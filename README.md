# Anjielo Intercom — Home Assistant integration

A **100% local** Home Assistant integration for the Anjielo video intercom (Tuya monitor
`DEKCE_IDS07_KXT_M70`), through the **Anjielo bridge**: a Go program that holds the monitor's only
local session and exposes an HTTP API and an RTSP stream.

> This repository only contains the Home Assistant integration. The bridge is not published here.

## Features
One "Intercom" device with:
- **Camera**: H.264 720p video plus the door station's audio, opened on demand (WebRTC through Home
  Assistant's go2rtc, or HLS);
- **Events**: doorbell, motion, alert, lock opened, gate opened;
- **Event photos**: doorbell, motion, alert;
- **Buttons**: open the lock, open the gate;
- **Settings**: motion detection, detection zone, motion sensitivity, alarm interval;
- **Diagnostics**: SD card, doors, monitoring zone.

Updates are pushed live (Server-Sent Events): no polling, no cloud.

## Installation (HACS)
1. HACS → ⋮ → **Custom repositories** → `https://github.com/raphaelh/ha-anjielo`, type **Integration**.
2. Download **Anjielo Intercom**, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → "Anjielo Intercom":
   bridge host, API port (`8565`), RTSP port (`8564`), bridge token.

To move the bridge to another host: ⋮ → **Reconfigure** on the integration (entities and history are kept).

## Notes
- The camera never opens the stream just for a thumbnail: on dashboards, prefer a *Picture* card on
  "Doorbell photo" that opens the camera when tapped.
- If the camera stays on HLS or shows "Stream source is not supported by go2rtc", reload Home Assistant's
  **go2rtc** integration.
