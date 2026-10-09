#!/bin/sh
set -eu

Xvfb :99 -screen 0 1440x900x24 -nolisten tcp &
xvfb_pid=$!
app_pid=''
wm_pid=''
vnc_pid=''
web_pid=''
cleanup() {
    for pid in "$app_pid" "$web_pid" "$vnc_pid" "$wm_pid" "$xvfb_pid"; do
        if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; fi
    done
    for pid in "$app_pid" "$web_pid" "$vnc_pid" "$wm_pid" "$xvfb_pid"; do
        if [ -n "$pid" ]; then wait "$pid" 2>/dev/null || true; fi
    done
}
trap cleanup EXIT
trap 'exit 0' TERM INT

count=0
while ! xdpyinfo -display :99 >/dev/null 2>&1; do
    kill -0 "$xvfb_pid" 2>/dev/null || exit 1
    count=$((count + 1))
    if [ "$count" -ge 100 ]; then exit 1; fi
    sleep 0.1
done
openbox &
wm_pid=$!
x11vnc -display :99 -forever -shared -nopw -localhost -rfbport 5900 -quiet &
vnc_pid=$!
websockify --web=/usr/share/novnc 6080 localhost:5900 &
web_pid=$!
python -m providence &
app_pid=$!
wait "$app_pid"
