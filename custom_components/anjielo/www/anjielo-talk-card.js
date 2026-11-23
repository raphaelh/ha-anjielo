/*
 * Anjielo intercom card: live video with a "Talk" button, as in the vendor app.
 *
 * One WebRTC session, opened with the card, through Home Assistant's own WebRTC
 * path (camera/webrtc/* websocket commands, served by HA's built-in go2rtc), on
 * the integration's "Talk" camera: the bridge's push-to-talk stream (video,
 * sound and a backchannel for the microphone).
 *
 * "Talk" only attaches the phone's microphone to that running session; "Stop"
 * detaches it. The bridge opens the call on the intercom (start-talk: you hear
 * the gate, your voice goes to its speaker) when voice arrives on the
 * backchannel, and closes it after a short silence. Nothing is negotiated when
 * talk starts or stops, so it is immediate even on a mobile link, and the
 * picture never stops.
 *
 * Browsers give the microphone to secure pages only: open Home Assistant over
 * HTTPS (the companion app included).
 *
 *   type: custom:anjielo-talk-card
 *   talk_entity: camera.intercom_talk  # video, sound, microphone
 *   sd_entity: camera.intercom_talk_sd # optional: the same in SD (slow links)
 *   quality_entity: select.intercom_video_quality  # optional: the integration's HD/SD setting
 *   (sd_entity and quality_entity are found on talk_entity's device when not given;
 *    the card follows the setting, changed in the integration, with its upload test)
 *   entity: camera.intercom            # optional: video only, used without talk_entity
 *   open_buttons: [gate, lock]         # optional: open buttons under the video, among
 *                                      # gate and lock (found on talk_entity's device;
 *                                      # default: both; [] for none). Also in the card editor.
 *   debug: true                        # optional: show connection steps and timings
 *   labels:                            # optional, to translate the buttons
 *     talk: Talk
 *     stop: Stop
 *     sound_on: Sound on
 *     connecting: Connecting…
 *     no_microphone: "No microphone: listening only"
 *     needs_https: "The microphone needs HTTPS: open Home Assistant at its https address"
 *     open_gate: Open gate
 *     open_lock: Open door
 *     confirm: Tap again to open    # an open button asks for a second tap
 */

const VERSION = "0.9.0";

const DEFAULT_LABELS = {
  talk: "Talk",
  stop: "Stop",
  sound_on: "Sound on",
  connecting: "Connecting…",
  no_microphone: "No microphone: listening only",
  needs_https: "The microphone needs HTTPS: open Home Assistant at its https address",
  open_gate: "Open gate",
  open_lock: "Open door",
  confirm: "Tap again to open",
};

/* Open buttons the card can show: the integration's button entities. */
const OPEN_BUTTONS = [
  { key: "gate", translation_key: "open_gate", icon: "mdi:gate-open" },
  { key: "lock", translation_key: "open_lock", icon: "mdi:lock-open-variant" },
];
const CONFIRM_MS = 4000;

/* WebRTC client configuration per camera, fetched once per page. */
const clientConfigs = new Map();
function clientConfig(hass, entity) {
  if (!clientConfigs.has(entity)) {
    const p = hass
      .callWS({ type: "camera/webrtc/get_client_config", entity_id: entity })
      .catch((err) => {
        clientConfigs.delete(entity); // retry next time
        throw err;
      });
    clientConfigs.set(entity, p);
  }
  return clientConfigs.get(entity);
}

/* One WebRTC session with a camera entity through Home Assistant. */
class HaWebRTC {
  constructor(hass, entity, { talk, onTrack, onState, onError, onNote }) {
    this.hass = hass;
    this.entity = entity;
    this.talk = talk; // offer a microphone track (sendrecv audio)
    this.onTrack = onTrack;
    this.onState = onState;
    this.onError = onError;
    this.onNote = onNote || (() => {});
    this.closed = false;
    this.session = null;
    this.pending = [];
    this.unsub = null;
    this.pc = null;
    this.audio = null; // the sendrecv audio transceiver (talk)
    this.micTrack = null;
    this.t0 = Date.now();
    this.history = [];
  }

  note(what) {
    this.history.push(`${what}@${((Date.now() - this.t0) / 1000).toFixed(1)}s`);
    this.onNote(this);
  }

  /* Attach (track) or detach (null) the microphone: no renegotiation. */
  setMic(track) {
    this.micTrack = track;
    if (this.audio) {
      this.audio.sender.replaceTrack(track).catch((err) => this.onError(err.message || String(err)));
    }
    this.note(track ? "mic:on" : "mic:off");
  }

  /* Short text for a failure report: state history and the candidate pair in use. */
  async diagnose() {
    const pc = this.pc;
    let pair = "no pair";
    if (pc) {
      try {
        const st = await pc.getStats();
        st.forEach((r) => {
          if (r.type === "candidate-pair" && r.nominated) {
            const l = st.get(r.localCandidateId);
            const m = st.get(r.remoteCandidateId);
            pair = `${l ? l.candidateType + "/" + l.protocol : "?"} -> ${m ? (m.address || m.ip) + ":" + m.port + "/" + m.protocol : "?"} (${r.state})`;
          }
        });
      } catch (_) {}
    }
    return `${this.history.join(" ")} | ${pair}`;
  }

  async open() {
    const client = await clientConfig(this.hass, this.entity);
    if (this.closed) return;
    const pc = new RTCPeerConnection(client.configuration || {});
    this.pc = pc;
    pc.addTransceiver("video", { direction: "recvonly" });
    if (this.talk) {
      // sendrecv: the gate's sound comes in on it; the microphone goes out on it
      // once attached (replaceTrack), without a new negotiation.
      this.audio = pc.addTransceiver(this.micTrack || "audio", { direction: "sendrecv" });
    }
    pc.ontrack = (ev) => this.onTrack(ev.track);
    pc.onicegatheringstatechange = () => this.note(`gather:${pc.iceGatheringState}`);
    pc.onicecandidate = (ev) => {
      if (!ev.candidate || this.closed) return;
      const c = { candidate: ev.candidate.candidate, sdpMid: ev.candidate.sdpMid,
                  sdpMLineIndex: ev.candidate.sdpMLineIndex };
      if (this.session) this.sendCandidate(c);
      else this.pending.push(c);
    };
    pc.oniceconnectionstatechange = () => this.note(`ice:${pc.iceConnectionState}`);
    pc.onconnectionstatechange = () => {
      this.note(`pc:${pc.connectionState}`);
      if (!this.closed) this.onState(pc.connectionState);
    };
    this.note("offer");
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    if (this.closed) return;
    const unsub = await this.hass.connection.subscribeMessage(
      (msg) => this.signal(msg),
      { type: "camera/webrtc/offer", entity_id: this.entity, offer: offer.sdp },
    );
    if (this.closed) unsub();
    else this.unsub = unsub;
  }

  async signal(msg) {
    if (this.closed || !this.pc) return;
    try {
      switch (msg.type) {
        case "session":
          this.note("session");
          this.session = msg.session_id;
          for (const c of this.pending.splice(0)) this.sendCandidate(c);
          break;
        case "answer":
          this.note("answer");
          await this.pc.setRemoteDescription({ type: "answer", sdp: msg.answer });
          break;
        case "candidate":
          await this.pc.addIceCandidate(msg.candidate);
          break;
        case "error":
          this.onError(`${msg.code}: ${msg.message}`);
          break;
      }
    } catch (err) {
      this.onError(err.message || String(err));
    }
  }

  sendCandidate(candidate) {
    this.hass
      .callWS({ type: "camera/webrtc/candidate", entity_id: this.entity,
                session_id: this.session, candidate })
      .catch(() => {});
  }

  close() {
    this.closed = true;
    if (this.unsub) {
      try {
        this.unsub(); // HA closes the WebRTC session
      } catch (_) {}
      this.unsub = null;
    }
    if (this.pc) this.pc.close();
    this.pc = null;
  }
}

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .view { position: relative; background: #000; aspect-ratio: 16 / 9; }
  video { width: 100%; height: 100%; object-fit: contain; display: block; }
  .status { position: absolute; inset: 0; display: flex; align-items: center;
            justify-content: center; color: #fff; text-align: center; padding: 16px;
            pointer-events: none; text-shadow: 0 1px 3px #000; }
  .notice { position: absolute; left: 0; right: 0; top: 0; padding: 6px 12px;
            background: rgba(0, 0, 0, .6); color: #fff; font-size: 13px; white-space: pre-wrap; }
  .talk { position: absolute; right: 12px; bottom: 12px; border: 0; border-radius: 28px;
          padding: 12px 18px; font: inherit; font-weight: 500; cursor: pointer;
          display: flex; align-items: center; gap: 8px; color: #fff;
          background: rgba(0, 0, 0, .55); box-shadow: 0 2px 6px rgba(0, 0, 0, .4); }
  .talk ha-icon { --mdc-icon-size: 24px; }
  .talk.on { background: var(--error-color, #db4437); }
  .sound { position: absolute; left: 12px; bottom: 12px; border: 0; border-radius: 20px;
           padding: 8px 14px; font: inherit; cursor: pointer; color: #fff;
           background: rgba(0, 0, 0, .55); }
  .actions { display: flex; gap: 8px; padding: 8px; }
  .actions[hidden] { display: none; }
  .open { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px;
          min-height: 48px; padding: 8px 12px; border-radius: 12px; cursor: pointer;
          font: inherit; font-weight: 500; color: var(--primary-text-color);
          background: var(--secondary-background-color, rgba(127, 127, 127, .12));
          border: 1px solid var(--divider-color, rgba(127, 127, 127, .25)); }
  .open ha-icon { --mdc-icon-size: 22px; color: var(--state-icon-color, var(--primary-color)); }
  .open.confirm { background: var(--warning-color, #ffa600); color: #fff; border-color: transparent; }
  .open.confirm ha-icon { color: #fff; }
  .open:disabled { opacity: .45; cursor: default; }
  [hidden] { display: none !important; }
`;

class AnjieloTalkCard extends HTMLElement {
  constructor() {
    super();
    this._rtc = null;
    this._state = "idle"; // idle | connecting | connected
    this._talking = false;
    this._mic = null; // the microphone MediaStream while talking
    this._openEntities = {}; // gate / lock -> button entity, found on talk_entity's device
    this._confirming = null; // the open button waiting for its second tap
    this._onVisibility = () => {
      if (document.visibilityState === "hidden") this._stop();
      else if (this.isConnected) this._autoOpen();
    };
  }

  static getStubConfig(hass) {
    const talk = Object.values(hass.entities || {}).find((e) => e.platform === "anjielo" && e.translation_key === "talk");
    if (talk) return { talk_entity: talk.entity_id };
    const cams = Object.keys(hass.states).filter((e) => e.startsWith("camera."));
    return { talk_entity: cams.find((e) => e.endsWith("_talk")) || cams[0] || "" };
  }

  /* The card editor (HA's own form): camera and open buttons. */
  static getConfigForm() {
    return {
      schema: [
        { name: "talk_entity", required: true,
          selector: { entity: { domain: "camera", integration: "anjielo" } } },
        { name: "open_buttons",
          selector: { select: { multiple: true, mode: "list", options: OPEN_BUTTONS.map((b) => ({
            value: b.key, label: DEFAULT_LABELS[b.translation_key] })) } } },
      ],
      computeLabel: (s) => ({ talk_entity: "Talk camera", open_buttons: "Open buttons" })[s.name],
      computeHelper: (s) => s.name === "open_buttons"
        ? "Shown under the video, each opens on a second tap" : undefined,
    };
  }

  setConfig(config) {
    const cam = (v) => typeof v === "string" && v.startsWith("camera.");
    if (!config || !(cam(config.talk_entity) || cam(config.entity))) {
      throw new Error("talk_entity: the Anjielo Talk camera is required");
    }
    this._config = config;
    this._canTalk = cam(config.talk_entity);
    this._sdEntity = cam(config.sd_entity) ? config.sd_entity : cam(config.lite_entity) ? config.lite_entity : null;
    this._hasLite = this._canTalk && !!this._sdEntity;
    this._qualityEntity = typeof config.quality_entity === "string" && config.quality_entity.startsWith("select.")
      ? config.quality_entity : null;
    this._siblingsDone = false;
    this._labels = { ...DEFAULT_LABELS, ...(config.labels || {}) };
    const wanted = Array.isArray(config.open_buttons) ? config.open_buttons : OPEN_BUTTONS.map((b) => b.key);
    this._openButtons = OPEN_BUTTONS.filter((b) => wanted.includes(b.key));
    this._openEntities = {};
    this._confirming = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._findSiblings();
    if (this.isConnected && !this._rtc) this._autoOpen();
    else if (this._rtc && this._qualityEntity && this._lite() !== this._openedLite) {
      this._open(); // the video quality setting changed (here or on another screen)
    }
    this._update();
  }

  getCardSize() {
    return 5;
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._onVisibility);
    if (this._hass && this._config && !this._rtc) this._autoOpen();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    this._stop(); // leaving the page ends the view and any call
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `
        <style>${STYLE}</style>
        <ha-card>
          <div class="view">
            <video playsinline autoplay muted></video>
            <audio autoplay></audio>
            <div class="status" id="status"></div>
            <div class="notice" id="notice" hidden></div>
            <button class="sound" id="sound" hidden></button>
            <button class="talk" id="talk"><ha-icon></ha-icon><span></span></button>
          </div>
          <div class="actions" id="actions" hidden></div>
        </ha-card>`;
      this._video = this.shadowRoot.querySelector("video");
      this._audio = this.shadowRoot.querySelector("audio");
      this._$("talk").addEventListener("click", () => this._toggleTalk());
      this._$("sound").addEventListener("click", () => {
        this._audio.play().catch(() => {});
        this._$("sound").hidden = true;
      });
    }
    this._update();
  }

  _$(id) {
    return this.shadowRoot.getElementById(id);
  }

  _update(error) {
    if (!this.shadowRoot) return;
    const L = this._labels;
    const talk = this._$("talk");
    talk.hidden = !this._canTalk;
    talk.querySelector("span").textContent = this._talking ? L.stop : L.talk;
    talk.querySelector("ha-icon").icon = this._talking ? "mdi:phone-hangup" : "mdi:microphone";
    talk.classList.toggle("on", this._talking);
    this._$("sound").textContent = L.sound_on;
    this._updateActions();
    if (error !== undefined) this._error = error;
    const status = this._$("status");
    status.textContent = this._error || (this._state === "connecting" ? L.connecting : "");
    status.hidden = !status.textContent;
  }

  /* The open buttons row: one button per chosen entity found on the device. */
  _updateActions() {
    const row = this._$("actions");
    const shown = (this._openButtons || []).filter((b) => this._openEntities[b.key]);
    const keys = shown.map((b) => b.key).join(",");
    if (row.dataset.keys !== keys) {
      row.dataset.keys = keys;
      row.replaceChildren(...shown.map((b) => {
        const btn = document.createElement("button");
        btn.className = "open";
        btn.dataset.key = b.key;
        btn.append(document.createElement("ha-icon"), document.createElement("span"));
        btn.addEventListener("click", () => this._openPress(b.key));
        return btn;
      }));
    }
    row.hidden = !shown.length;
    for (const btn of row.children) {
      const b = OPEN_BUTTONS.find((x) => x.key === btn.dataset.key);
      const entity = this._openEntities[b.key];
      const st = this._hass && this._hass.states[entity];
      const confirm = this._confirming === b.key;
      btn.classList.toggle("confirm", confirm);
      btn.disabled = !st || st.state === "unavailable";
      btn.querySelector("ha-icon").icon = b.icon;
      btn.querySelector("span").textContent = confirm ? this._labels.confirm : this._labels[b.translation_key];
    }
  }

  /* First tap arms the button, a second one within a few seconds opens. */
  _openPress(key) {
    clearTimeout(this._confirmTimer);
    if (this._confirming !== key) {
      this._confirming = key;
      this._confirmTimer = setTimeout(() => {
        this._confirming = null;
        this._update();
      }, CONFIRM_MS);
      this._update();
      return;
    }
    this._confirming = null;
    this._update();
    this._hass.callService("button", "press", { entity_id: this._openEntities[key] }).catch((err) => {
      this._notice(err.message || String(err));
    });
  }

  _notice(text) {
    const n = this._$("notice");
    n.textContent = text || "";
    n.hidden = !text;
  }

  _debugNote() {
    if (!this._config || !this._config.debug || !this._rtc) return;
    this._notice([this._rtc.history.join(" "), this._audioStats || ""].filter(Boolean).join("\n"));
  }

  /* Debug: received audio every 2 s (losses, concealed holes, jitter), to
     tell network cuts from silence sent by the intercom. */
  async _pollAudioStats() {
    const pc = this._rtc && this._rtc.pc;
    if (!pc) return;
    const st = await pc.getStats();
    let a = null;
    let proto = "?";
    st.forEach((r) => {
      if (r.type === "inbound-rtp" && r.kind === "audio") a = r;
      if (r.type === "candidate-pair" && r.nominated && r.state === "succeeded") {
        const l = st.get(r.localCandidateId);
        if (l) proto = l.protocol;
      }
    });
    if (!a) return;
    const prev = this._audioPrev || a;
    const dt = Math.max((a.timestamp - prev.timestamp) / 1000, 0.001);
    const recv = (a.totalSamplesReceived || 0) - (prev.totalSamplesReceived || 0);
    const conc = (a.concealedSamples || 0) - (prev.concealedSamples || 0);
    const silent = (a.silentConcealedSamples || 0) - (prev.silentConcealedSamples || 0);
    this._audioPrev = a;
    this._audioStats = `${this._openedLite ? "sd" : "hd"} audio (${proto}): ${a.packetsReceived} pkts, lost ${a.packetsLost}, ` +
      `jitter ${Math.round((a.jitter || 0) * 1000)} ms, ` +
      `concealed ${recv ? Math.round((100 * conc) / recv) : 0}% (silent ${recv ? Math.round((100 * silent) / recv) : 0}%), ` +
      `level ${(a.audioLevel || 0).toFixed(2)}, ${(dt).toFixed(0)} s`;
    this._debugNote();
  }

  /* SD video? As set in the integration's video quality setting. */
  _lite() {
    if (!this._hasLite || !this._qualityEntity) return false;
    const st = this._hass && this._hass.states[this._qualityEntity];
    return !!st && st.state === "sd";
  }

  /* sd_entity / quality_entity not given: take them from talk_entity's device
     (the integration's "talk_sd" camera and "video_quality" setting). A
     disabled SD camera is not listed: HD only. */
  _findSiblings() {
    if (this._siblingsDone || !this._canTalk || !this._hass || !this._hass.entities) return;
    this._siblingsDone = true;
    const ents = this._hass.entities;
    const talk = ents[this._config.talk_entity];
    if (!talk || !talk.device_id) return;
    const sibling = (domain, key) => Object.values(ents).find((e) => e.device_id === talk.device_id &&
      e.platform === talk.platform && e.translation_key === key && e.entity_id.startsWith(domain + "."));
    if (!this._sdEntity) {
      const sd = sibling("camera", "talk_sd");
      if (sd) {
        this._sdEntity = sd.entity_id;
        this._hasLite = true;
      }
    }
    if (!this._qualityEntity) {
      const q = sibling("select", "video_quality");
      if (q) this._qualityEntity = q.entity_id;
    }
    for (const b of OPEN_BUTTONS) {
      const e = sibling("button", b.translation_key);
      if (e) this._openEntities[b.key] = e.entity_id;
    }
  }

  /* Open the session when nothing runs; after a failure, wait before trying again. */
  _autoOpen() {
    if (this._failedAt && Date.now() - this._failedAt < 15000) return;
    this._open();
  }

  _open() {
    if (!this._hass || !this._config || document.visibilityState === "hidden") return;
    this._close();
    this._state = "connecting";
    this._update("");
    const lite = this._lite();
    this._openedLite = lite;
    const entity = !this._canTalk ? this._config.entity : lite ? this._sdEntity : this._config.talk_entity;
    let picture = null; // set on the <video> with its first track: the last picture stays meanwhile
    const rtc = new HaWebRTC(this._hass, entity, {
      talk: this._canTalk,
      onTrack: (track) => {
        if (rtc !== this._rtc) return;
        if (track.kind === "audio") {
          this._audio.srcObject = new MediaStream([track]);
          this._audio.play().catch(() => {}); // allowed once the user tapped Talk
          return;
        }
        if (!picture) {
          picture = new MediaStream();
          this._video.srcObject = picture;
          this._video.addEventListener("playing", () => rtc.note("playing"), { once: true });
        }
        picture.addTrack(track);
        this._video.play().catch(() => {});
      },
      onState: (state) => {
        if (rtc !== this._rtc) return;
        if (state === "connected") {
          this._failedAt = 0;
          this._state = "connected";
          this._update();
        } else if (state === "failed") {
          rtc.diagnose().then((d) => {
            if (rtc === this._rtc) this._fail(`WebRTC connection failed: ${d}`);
          });
        }
      },
      onError: (msg) => {
        if (rtc === this._rtc) this._fail(msg);
      },
      onNote: () => this._debugNote(),
    });
    if (this._mic) rtc.setMic(this._mic.getAudioTracks()[0]);
    this._rtc = rtc;
    clearInterval(this._statsTimer);
    this._audioPrev = null;
    this._audioStats = "";
    if (this._config.debug) {
      this._statsTimer = setInterval(() => this._pollAudioStats().catch(() => {}), 2000);
    }
    rtc.open().catch((err) => {
      if (rtc === this._rtc) this._fail(err.message || String(err));
    });
  }

  _close() {
    clearInterval(this._statsTimer);
    if (this._rtc) this._rtc.close();
    this._rtc = null;
    this._state = "idle";
  }

  _fail(error) {
    this._failedAt = Date.now();
    this._close();
    this._stopMic();
    this._update(error);
  }

  async _toggleTalk() {
    if (this._talking) {
      this._stopMic();
      this._update();
      return;
    }
    // Inside the tap: a phone lets a page play sound only from a user gesture.
    this._audio.play().catch(() => {
      if (this._audio.srcObject) this._$("sound").hidden = false;
    });
    this._talking = true;
    this._notice("");
    this._update();
    if (!window.isSecureContext || !navigator.mediaDevices) {
      // Plain http (such as the companion app on its local address): browsers
      // offer no microphone at all there.
      this._talking = false;
      this._notice(this._labels.needs_https);
      this._update();
      return;
    }
    let mic = null;
    try {
      mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (err) {
      // Refused, or page not on HTTPS: no voice, so no call either.
      this._talking = false;
      this._notice(`${this._labels.no_microphone} (${err.name || err})`);
      this._update();
      return;
    }
    if (!this._talking) {
      for (const t of mic.getTracks()) t.stop(); // stopped while asking
      return;
    }
    this._mic = mic;
    if (this._rtc) this._rtc.setMic(mic.getAudioTracks()[0]);
    else this._autoOpen();
  }

  _stopMic() {
    if (this._rtc && this._mic) this._rtc.setMic(null); // the bridge ends the call after a short silence
    if (this._mic) for (const t of this._mic.getTracks()) t.stop();
    this._mic = null;
    this._talking = false;
  }

  _stop() {
    this._stopMic();
    this._close();
    if (this._video) this._video.srcObject = null;
    if (this._audio) this._audio.srcObject = null;
    this._update();
  }
}

if (!customElements.get("anjielo-talk-card")) {
  customElements.define("anjielo-talk-card", AnjieloTalkCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "anjielo-talk-card",
    name: "Anjielo intercom",
    description: "Live video with a Talk button (sound and microphone, needs HTTPS) and open gate / door buttons.",
  });
  console.info(`anjielo-talk-card ${VERSION}`);
}
