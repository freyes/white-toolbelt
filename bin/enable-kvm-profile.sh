#!/usr/bin/env bash
#
# enable-kvm-profile.sh
#
# Creates an LXD "virt" profile in a given project that enables nested
# virtualization (KVM), then assigns that profile to every container already
# present in the project.
#
# Usage:
#   ./enable-kvm-profile.sh <project>
#
# Where <project> is the LXD project name. Running in a project context is
# required because LXD inherits profiles from the project when at least one
# profile is defined on it (otherwise the "default" project's profiles leak in).
#
# Example:
#   ./enable-kvm-profile.sh my-project
#

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROFILE_NAME="${PROFILE_NAME:-virt}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
die() {
    echo "ERROR: $*" >&2
    exit 1
}

info() {
    echo "[*] $*"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    cat >&2 <<'EOF'
Usage: ./enable-kvm-profile.sh <project>

Creates the KVM ("virt") profile in the given project and assigns it to
every container in that project.
EOF
    exit 1
fi

PROJECT="$1"

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
command -v lxc >/dev/null 2>&1 || die "lxc CLI not found. Install LXD first."

lxc project show "$PROJECT" >/dev/null 2>&1 \
    || die "Project '$PROJECT' does not exist. Create it with: lxc project create $PROJECT"

info "Operating on project '$PROJECT'"

# ---------------------------------------------------------------------------
# Create (or update) the KVM profile
# ---------------------------------------------------------------------------
if lxc profile show --project "$PROJECT" "$PROFILE_NAME" >/dev/null 2>&1; then
    info "Profile '$PROFILE_NAME' already exists in project '$PROJECT'; updating it."
else
    info "Creating profile '$PROFILE_NAME' in project '$PROJECT'"
    lxc profile create --project "$PROJECT" "$PROFILE_NAME"
fi

# Enable nesting (required for nested virtualization).
info "Enabling security.nesting on profile '$PROFILE_NAME'"
lxc profile set --project "$PROJECT" "$PROFILE_NAME" security.nesting true

# Pass through the character devices KVM/QEMU needs.
# These names are stable so re-adding is idempotent (LXD overwrites existing
# devices with the same name).
info "Attaching virtualization devices to profile '$PROFILE_NAME'"
lxc profile device add --project "$PROJECT" "$PROFILE_NAME" kvm         unix-char source=/dev/kvm
lxc profile device add --project "$PROJECT" "$PROFILE_NAME" vhost-net   unix-char source=/dev/vhost-net
lxc profile device add --project "$PROJECT" "$PROFILE_NAME" vhost-vsock unix-char source=/dev/vhost-vsock
lxc profile device add --project "$PROJECT" "$PROFILE_NAME" tun         unix-char source=/dev/net/tun

info "Profile '$PROFILE_NAME' is ready:"
lxc profile show --project "$PROJECT" "$PROFILE_NAME"

# ---------------------------------------------------------------------------
# Assign the profile to all containers in the project
# ---------------------------------------------------------------------------
info "Discovering containers in project '$PROJECT'"

# --format=json avoids parsing the human-readable table.
mapfile -t CONTAINERS < <(lxc list --project "$PROJECT" --format=json | jq -r '.[].name // empty')

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
    info "No containers found in project '$PROJECT'. Nothing to assign."
    exit 0
fi

for c in "${CONTAINERS[@]}"; do
    # Skip if the profile is already applied, to avoid redundant restarts.
    if lxc config show --project "$PROJECT" "$c" 2>/dev/null | jq -e --arg p "$PROFILE_NAME" '.profiles | index($p)' >/dev/null; then
        info "Container '$c' already has profile '$PROFILE_NAME'; skipping."
        continue
    fi

    info "Assigning profile '$PROFILE_NAME' to container '$c'"
    lxc profile assign --project "$PROJECT" "$c" "$PROFILE_NAME"
    ASSIGNED[$c]=1
done

# ---------------------------------------------------------------------------
# Restart containers that were assigned the profile (nesting + devices only
# take effect after a restart).
# ---------------------------------------------------------------------------
if [[ ${#ASSIGNED[@]:-0} -gt 0 ]]; then
    info "Restarting containers to apply the new profile..."
    for c in "${!ASSIGNED[@]}"; do
        if lxc info --project "$PROJECT" "$c" >/dev/null 2>&1; then
            info "Restarting container '$c'"
            lxc restart --project "$PROJECT" "$c"
        else
            info "Container '$c' not running; it will pick up the profile on next start."
        fi
    done
else
    info "No containers required a new assignment."
fi

info "Done. Verify with: lxc config show <container> | grep -A1 profiles"