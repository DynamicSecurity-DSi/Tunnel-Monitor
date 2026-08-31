#!/usr/bin/env bash
# monitor-manage.sh
# Interactive management menu for the tunnel monitor.
#
# Run it with no arguments — it opens the menu:
#   ./monitor-manage.sh
#
# Edits the nested-schema config (vpn_sites / twingate.connectors / slack) and
# drives the container via docker compose.
#
# Paths default to this script's own directory; override with env vars if needed:
#   CONFIG_FILE   (default: <script dir>/config.json)
#   COMPOSE_FILE  (default: <script dir>/docker-compose.yml)
#   CONTAINER     (default: tunnel-monitor)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$SCRIPT_DIR/config.json}"
COMPOSE_FILE="${COMPOSE_FILE:-$SCRIPT_DIR/docker-compose.yml}"
CONTAINER="${CONTAINER:-tunnel-monitor}"

export CONFIG_FILE   # the python helpers below read it from the environment

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found at $CONFIG_FILE"
    exit 1
fi

main_menu() {
    echo ""
    echo "════════════════════════════════════════"
    echo "  Tunnel Monitor Management"
    echo "════════════════════════════════════════"
    echo ""
    echo "1. View all monitored sites"
    echo "2. Add new site/connector"
    echo "3. Edit existing connector"
    echo "4. Remove connector"
    echo "5. Restart monitor"
    echo "6. View monitor logs"
    echo "7. Exit"
    echo ""
    read -p "Select (1-7): " choice

    case $choice in
        1) view_connectors ;;
        2) add_connector ;;
        3) edit_connector ;;
        4) remove_connector ;;
        5) restart_monitor ;;
        6) view_logs ;;
        7) echo "Exit"; exit 0 ;;
        *) echo "Invalid selection"; main_menu ;;
    esac
}

view_connectors() {
    echo ""
    echo "=== Current Monitored Sites ==="
    echo ""

    python3 <<'PYTHON_EOF'
import json, os

config_file = os.environ["CONFIG_FILE"]
with open(config_file) as f:
    config = json.load(f)

ci = config.get("check_interval", 0)
ri = config.get("report_interval", 0)
print(f"Check interval: {ci}s (every {ci // 60} min)")
print(f"Report interval: {ri}s (every {ri // 3600} hr)")
print(f"Slack enabled: {config.get('slack', {}).get('enabled')}")
print("")

vpn_sites = config.get("vpn_sites", [])
if vpn_sites:
    print(f"\U0001F517 VPN SITES: {len(vpn_sites)}")
    for i, site in enumerate(vpn_sites, 1):
        print(f"  {i}. {site['name']}")
        for addr in site.get("addresses", []):
            ip = addr["ip"] if isinstance(addr, dict) else addr
            print(f"     - {ip}")
    print("")

connectors = config.get("twingate", {}).get("connectors", [])
if connectors:
    print(f"\U0001F310 EDGE NODES: {len(connectors)}")
    for i, conn in enumerate(connectors, 1):
        print(f"  {i}. {conn['name']} @ {conn['ip']}")
        ports = conn.get("test_ports", [])
        print(f"     Ports: {', '.join(map(str, ports)) if ports else '(ping only)'}")
    print("")

total = len(vpn_sites) + len(connectors)
print(f"Total: {total} monitored items")
PYTHON_EOF

    read -p "Press Enter to continue..."
    main_menu
}

add_connector() {
    echo ""
    echo "=== Add New Site ==="
    echo ""
    echo "1. VPN Site"
    echo "2. Edge Node (Twingate Connector)"
    echo ""
    read -p "Select (1-2): " site_type

    if [ "$site_type" = "1" ]; then
        add_vpn_site
    elif [ "$site_type" = "2" ]; then
        add_edge_node
    else
        echo "Invalid selection"
        add_connector
    fi
}

add_vpn_site() {
    echo ""
    read -p "Site name (e.g., customer-a-vpn): " site_name
    read -p "Description (e.g., Customer A VPN): " description
    read -p "IP addresses (comma-separated): " ips_input

    if [ -z "$site_name" ] || [ -z "$ips_input" ]; then
        echo "Error: Name and IPs required"
        main_menu
        return
    fi

    echo ""
    echo "Adding VPN site: $site_name"
    echo "IPs: $ips_input"
    read -p "Continue? (y/n) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        SITE_NAME="$site_name" DESCRIPTION="$description" IPS_INPUT="$ips_input" \
        python3 <<'PYTHON_EOF'
import json, os

config_file = os.environ["CONFIG_FILE"]
with open(config_file) as f:
    config = json.load(f)

ips = [ip.strip() for ip in os.environ["IPS_INPUT"].split(",") if ip.strip()]
new_site = {
    "name": os.environ["SITE_NAME"],
    "description": os.environ.get("DESCRIPTION", ""),
    "addresses": [{"ip": ip, "description": ip} for ip in ips],
}
config.setdefault("vpn_sites", []).append(new_site)

with open(config_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
print("✓ VPN site added")
PYTHON_EOF
        restart_monitor_auto
    fi
    main_menu
}

add_edge_node() {
    echo ""
    read -p "Site acronym (e.g., DSi, LAB, CLV): " site_acronym
    read -p "Site IP address: " site_ip

    if [ -z "$site_acronym" ] || [ -z "$site_ip" ]; then
        echo "Error: Site acronym and IP required"
        main_menu
        return
    fi

    connectors_to_add=()

    while true; do
        echo ""
        echo "Configure $site_acronym:"
        echo "  1. Add Edge Node Connector (ping only)"
        echo "  2. Add DICOM Service (ask for IP and port)"
        echo "  3. Add HL7 Service (ask for IP and ports)"
        echo "  4. Add Custom Service"
        echo "  5. Done"
        read -p "Select (1-5): " choice

        case $choice in
            1)
                connectors_to_add+=("$site_acronym-EdgeNode|Edge node connector for $site_acronym|$site_ip|")
                echo "✓ Added $site_acronym-EdgeNode (ping only)"
                ;;
            2)
                read -p "DICOM server IP: " dicom_ip
                read -p "DICOM port (default 4242): " dicom_port
                dicom_port=${dicom_port:-4242}
                if [ -n "$dicom_ip" ]; then
                    connectors_to_add+=("$site_acronym-DICOM|DICOM service at $site_acronym|$dicom_ip|$dicom_port")
                    echo "Added $site_acronym-DICOM @ $dicom_ip:$dicom_port"
                fi
                ;;
            3)
                read -p "HL7 server IP: " hl7_ip
                read -p "HL7 ports (default 8443,8201,8202,8203): " hl7_ports
                hl7_ports=${hl7_ports:-8443,8201,8202,8203}
                if [ -n "$hl7_ip" ]; then
                    connectors_to_add+=("$site_acronym-HL7|HL7 service at $site_acronym|$hl7_ip|$hl7_ports")
                    echo "Added $site_acronym-HL7 @ $hl7_ip:$hl7_ports"
                fi
                ;;
            4)
                read -p "Service name: " name
                read -p "Description: " desc
                read -p "Server IP: " svc_ip
                read -p "Ports (comma-separated, leave blank for ping only): " ports
                if [ -n "$name" ] && [ -n "$svc_ip" ]; then
                    connectors_to_add+=("$name|$desc|$svc_ip|$ports")
                    echo "Added $name @ $svc_ip"
                fi
                ;;
            5)
                if [ ${#connectors_to_add[@]} -eq 0 ]; then
                    echo "No services added, cancelled"
                    main_menu
                    return
                fi
                break
                ;;
            *)
                echo "Invalid selection"
                ;;
        esac
    done

    echo ""
    echo "Adding ${#connectors_to_add[@]} connector(s)..."
    read -p "Continue? (y/n) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        TEMP_CONNECTORS=$(mktemp)
        printf '%s\n' "${connectors_to_add[@]}" > "$TEMP_CONNECTORS"

        TEMP_CONNECTORS="$TEMP_CONNECTORS" python3 <<'PYTHON_EOF'
import json, os, re

config_file = os.environ["CONFIG_FILE"]
with open(config_file) as f:
    config = json.load(f)

with open(os.environ["TEMP_CONNECTORS"]) as f:
    lines = f.readlines()

count = 0
for line in lines:
    s = line.strip()
    if not s:
        continue
    parts = s.split("|")
    if len(parts) != 4:
        print(f"Skipping invalid: {s}")
        continue
    name, desc, ip, ports = parts
    ports = re.sub(r" +", ",", ports)
    ports_list = [int(p.strip()) for p in ports.split(",") if p.strip()]
    config.setdefault("twingate", {}).setdefault("connectors", []).append({
        "name": name,
        "description": desc,
        "ip": ip,
        "test_ports": ports_list,
    })
    count += 1

with open(config_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
print(f"✓ Added {count} connector(s)")
PYTHON_EOF

        rm -f "$TEMP_CONNECTORS"
        restart_monitor_auto
    fi
    main_menu
}

edit_connector() {
    echo ""
    echo "=== Edit Connector ==="
    echo ""

    python3 <<'PYTHON_EOF'
import json, os

config_file = os.environ["CONFIG_FILE"]
with open(config_file) as f:
    config = json.load(f)

connectors = config.get("twingate", {}).get("connectors", [])
if not connectors:
    print("(no connectors)")
print("Select connector to edit:\n")
for i, conn in enumerate(connectors, 1):
    print(f"{i}. {conn['name']}")
PYTHON_EOF

    read -p "Enter number (or q to quit): " choice

    if [ "$choice" = "q" ]; then
        main_menu
        return
    fi

    if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
        echo "Invalid input"
        edit_connector
        return
    fi

    echo ""
    echo "1. Edit description"
    echo "2. Edit IP address"
    echo "3. Edit ports"
    echo "4. Cancel"
    read -p "Select (1-4): " edit_choice

    case $edit_choice in
        1) read -p "New description: " new_value; field=description ;;
        2) read -p "New IP address: " new_value;   field=ip ;;
        3) read -p "New ports (comma or space separated): " new_value; field=ports ;;
        4) echo "Cancelled"; main_menu; return ;;
        *) echo "Invalid selection"; edit_connector; return ;;
    esac

    IDX="$choice" FIELD="$field" NEW_VALUE="$new_value" python3 <<'PYTHON_EOF'
import json, os, re

config_file = os.environ["CONFIG_FILE"]
idx = int(os.environ["IDX"]) - 1
field = os.environ["FIELD"]
val = os.environ["NEW_VALUE"]

with open(config_file) as f:
    config = json.load(f)

conn = config["twingate"]["connectors"][idx]
if field == "ports":
    ports_str = re.sub(r" +", ",", val)
    conn["test_ports"] = [int(p.strip()) for p in ports_str.split(",") if p.strip()]
else:
    conn[field] = val

with open(config_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
print("✓ Updated")
PYTHON_EOF

    restart_monitor_auto
    main_menu
}

remove_connector() {
    echo ""
    echo "=== Remove Connector ==="
    echo ""

    python3 <<'PYTHON_EOF'
import json, os

config_file = os.environ["CONFIG_FILE"]
with open(config_file) as f:
    config = json.load(f)

connectors = config.get("twingate", {}).get("connectors", [])
if not connectors:
    print("(no connectors)")
print("Select connector to remove:\n")
for i, conn in enumerate(connectors, 1):
    print(f"{i}. {conn['name']}")
PYTHON_EOF

    read -p "Enter number (or q to quit): " choice

    if [ "$choice" = "q" ]; then
        main_menu
        return
    fi

    if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
        echo "Invalid input"
        remove_connector
        return
    fi

    read -p "Confirm removal? (y/n) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        IDX="$choice" python3 <<'PYTHON_EOF'
import json, os

config_file = os.environ["CONFIG_FILE"]
idx = int(os.environ["IDX"]) - 1
with open(config_file) as f:
    config = json.load(f)
del config["twingate"]["connectors"][idx]
with open(config_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
print("✓ Removed")
PYTHON_EOF
        restart_monitor_auto
    fi
    main_menu
}

restart_monitor() {
    echo ""
    echo "Restarting monitor..."
    if ! docker compose -f "$COMPOSE_FILE" restart 2>/dev/null; then
        docker restart "$CONTAINER"
    fi
    sleep 2
    echo ""
    docker ps --filter "name=$CONTAINER"
    main_menu
}

restart_monitor_auto() {
    echo ""
    read -p "Restart monitor? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if docker compose -f "$COMPOSE_FILE" restart >/dev/null 2>&1 || docker restart "$CONTAINER" >/dev/null 2>&1; then
            echo "✓ Monitor restarted"
        fi
    fi
}

view_logs() {
    echo ""
    echo "Monitor logs (Ctrl+C to exit):"
    echo ""
    docker logs -f "$CONTAINER"
    main_menu
}

# Start
main_menu
