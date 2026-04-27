#!/bin/bash
# Auto-detect LAN IP and write it into mobile/app.json
cd "$(dirname "$0")"
[ -d venv ] || { echo "[ERROR] venv not found. Run ./setup.sh first."; exit 1; }
source venv/bin/activate
python -c "
import socket, json
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 53))
ip = s.getsockname()[0]
s.close()
print('Detected IP:', ip)
p = 'mobile/app.json'
d = json.load(open(p))
d['expo']['extra']['apiBaseUrl'] = f'http://{ip}:8000'
json.dump(d, open(p, 'w'), indent=2)
print(f'Updated {p} -> apiBaseUrl: http://{ip}:8000')
"
echo ""
echo "Done. Now: cd mobile && npx expo start --tunnel --clear"
