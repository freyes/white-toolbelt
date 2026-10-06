#!/bin/bash -eux

MAX_IO_READ="${MAX_IO_READ:-50MB}"
MAX_IO_WRITE="${MAX_IO_WRITE:-50MB}"
MAX_MEMORY="${MAX_MEMORY:-2GB}"
MAX_CPU="${MAX_CPU:-2}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTION]...

Apply resource limits to all instances in workshop.* LXD projects.

Default limits (applied when no limit option is given):
  limits.memory      ${MAX_MEMORY}
  limits.cpu          ${MAX_CPU}
  root limits.read    ${MAX_IO_READ}
  root limits.write   ${MAX_IO_WRITE}

Options:
  -m, --memory SIZE  Set memory limit only (e.g. 5G, 512MB). 0 to unset.
  -c, --cpus N       Set CPU core limit only (e.g. 4). 0 to unset.
  --disable          Unset all resource limits
  --status           Display current resource limits per instance
  -h, --help         Show this help message and exit
EOF
}

DISABLE=false
STATUS=false
MEMORY_SET=""
CPU_SET=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--memory)
            MEMORY_SET="$2"
            shift 2
            ;;
        -c|--cpus)
            CPU_SET="$2"
            shift 2
            ;;
        --disable)
            DISABLE=true
            shift
            ;;
        --status)
            STATUS=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ "$STATUS" = true ] && { [ "$DISABLE" = true ] || [ -n "$MEMORY_SET" ] || [ -n "$CPU_SET" ]; }; then
    echo "Error: --status cannot be combined with --disable, -m, or -c." >&2
    exit 1
fi

if [ "$DISABLE" = true ] && { [ -n "$MEMORY_SET" ] || [ -n "$CPU_SET" ]; }; then
    echo "Error: --disable cannot be combined with -m or -c." >&2
    exit 1
fi

# Determine which limits to apply
if [ "$DISABLE" = true ]; then
    APPLY_MEMORY=true
    APPLY_CPU=true
    APPLY_IO=true
elif [ -n "$MEMORY_SET" ] || [ -n "$CPU_SET" ]; then
    # Explicit flag mode: only touch what was requested
    [ -n "$MEMORY_SET" ] && APPLY_MEMORY=true || APPLY_MEMORY=false
    [ -n "$CPU_SET" ] && APPLY_CPU=true || APPLY_CPU=false
    APPLY_IO=false
else
    # Default mode: apply everything
    APPLY_MEMORY=true
    APPLY_CPU=true
    APPLY_IO=true
fi

WORKSHOP_PROJECTS=$(lxc project list -f json | jq '[.[] | select(.name | test("^workshop\\..*"))] | length')
WORKSHOP_PROJECTS=${WORKSHOP_PROJECTS:-0}

if [ "$WORKSHOP_PROJECTS" -eq 0 ]; then
    echo "No workshop projects found. Exiting."
    exit 0
fi

if [ "$STATUS" = true ]; then
    echo "Found $WORKSHOP_PROJECTS workshop projects. Displaying current limits..."
elif [ "$DISABLE" = true ]; then
    echo "Found $WORKSHOP_PROJECTS workshop projects. Disabling all limits..."
else
    echo "Found $WORKSHOP_PROJECTS workshop projects. Throttling instances..."
    if [ "$APPLY_MEMORY" = true ]; then
        echo "Max Memory: ${MEMORY_SET:-$MAX_MEMORY}"
    fi
    if [ "$APPLY_CPU" = true ]; then
        echo "Max CPU: ${CPU_SET:-$MAX_CPU}"
    fi
    if [ "$APPLY_IO" = true ]; then
        echo "Max IO Read: $MAX_IO_READ"
        echo "Max IO Write: $MAX_IO_WRITE"
    fi
fi

for project in $(lxc project list -f json | jq -r '.[] | select(.name | test("^workshop\\..*")) | .name'); do
    echo "Project: $project"
    for instance in $(lxc list --project "$project" -c n --format csv); do
        echo "  Instance: $instance"
        if [ "$STATUS" = true ]; then
            mem=$(lxc config get --project "$project" "$instance" limits.memory 2>/dev/null || true)
            cpu=$(lxc config get --project "$project" "$instance" limits.cpu 2>/dev/null || true)
            io_read=$(lxc config device get --project "$project" "$instance" root limits.read 2>/dev/null || true)
            io_write=$(lxc config device get --project "$project" "$instance" root limits.write 2>/dev/null || true)
            printf "    limits.memory:     %s\n" "${mem:-<not set>}"
            printf "    limits.cpu:        %s\n" "${cpu:-<not set>}"
            printf "    root limits.read:  %s\n" "${io_read:-<not set>}"
            printf "    root limits.write: %s\n" "${io_write:-<not set>}"
        else
            if [ "$APPLY_MEMORY" = true ]; then
                if [ "$DISABLE" = true ] || [ "$MEMORY_SET" = "0" ]; then
                    lxc config unset --project "$project" "$instance" limits.memory 2>/dev/null || /bin/true
                else
                    lxc config set --project "$project" "$instance" limits.memory "${MEMORY_SET:-$MAX_MEMORY}"
                fi
            fi
            if [ "$APPLY_CPU" = true ]; then
                if [ "$DISABLE" = true ] || [ "$CPU_SET" = "0" ]; then
                    lxc config unset --project "$project" "$instance" limits.cpu 2>/dev/null || /bin/true
                else
                    lxc config set --project "$project" "$instance" limits.cpu "${CPU_SET:-$MAX_CPU}"
                fi
            fi
            if [ "$APPLY_IO" = true ]; then
                if [ "$DISABLE" = true ]; then
                    lxc config device unset --project "$project" "$instance" root limits.read 2>/dev/null || /bin/true
                    lxc config device unset --project "$project" "$instance" root limits.write 2>/dev/null || /bin/true
                else
                    lxc config device set --project "$project" "$instance" root limits.read "${MAX_IO_READ}"
                    lxc config device set --project "$project" "$instance" root limits.write "${MAX_IO_WRITE}"
                fi
            fi
        fi
    done
done
