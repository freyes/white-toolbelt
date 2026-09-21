#!/bin/bash -eux


MAX_IO_READ="${MAX_IO_READ:-50MB}"
MAX_IO_WRITE="${MAX_IO_WRITE:-50MB}"
MAX_MEMORY="${MAX_MEMORY:-2GB}"
MAX_CPU="${MAX_CPU:-2}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTION]

Apply resource limits to all containers in workshop.* LXD projects.

Default limits (applied when no option is given):
  limits.memory      ${MAX_MEMORY}
  limits.cpu          ${MAX_CPU}
  root limits.read    ${MAX_IO_READ}
  root limits.write   ${MAX_IO_WRITE}

Options:
  --disable    Unset all resource limits instead of applying them
  -h, --help   Show this help message and exit
EOF
}

DISABLE=false
case "${1:-}" in
    --disable)
        DISABLE=true
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    "")
        ;;
    *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 1
        ;;
esac

WORKSHOP_PROJECTS=$(lxc project list -f json | jq '[.[] | select(.name | test("^workshop\\..*"))] | length')
WORKSHOP_PROJECTS=${WORKSHOP_PROJECTS:-0}

if [ "$WORKSHOP_PROJECTS" -eq 0 ]; then
    echo "No workshop projects found. Exiting."
    exit 0
fi

if [ "$DISABLE" = true ]; then
    echo "Found $WORKSHOP_PROJECTS workshop projects. Disabling all limits..."
else
    echo "Found $WORKSHOP_PROJECTS workshop projects. Throttling containers..."
    echo "Max IO Read: $MAX_IO_READ"
    echo "Max IO Write: $MAX_IO_WRITE"
    echo "Max Memory: $MAX_MEMORY"
    echo "Max CPU: $MAX_CPU"
fi

for project in $(lxc project list -f json | jq -r '.[] | select(.name | test("^workshop\\..*")) | .name'); do
    echo "Processing containers in project: $project"
    for container in $(lxc list --project "$project" -c n --format csv); do
        echo "Processing container: $container"
        if [ "$DISABLE" = true ]; then
            lxc config unset --project "$project" "$container" limits.memory
            lxc config unset --project "$project" "$container" limits.cpu
            lxc config device unset --project "$project" "$container" root limits.read
            lxc config device unset --project "$project" "$container" root limits.write
        else
            lxc config set --project "$project" "$container" limits.memory ${MAX_MEMORY}
            lxc config set --project "$project" "$container" limits.cpu ${MAX_CPU}
            lxc config device set --project "$project" "$container" root limits.read ${MAX_IO_READ}
            lxc config device set --project "$project" "$container" root limits.write ${MAX_IO_WRITE}
        fi
    done
done
