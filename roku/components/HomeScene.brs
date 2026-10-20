' Portada y reproductor. Mismo comportamiento que el front de la TV (tvlibre/web/app.js).

sub init()
    m.server = CreateObject("roAppInfo").GetValue("tvlibre_server")
    m.reg = CreateObject("roRegistrySection", "tvlibre")
    for each id in ["home", "bri", "clock", "msg", "rows", "video", "perr", "toast", "dim", "refresh", "retry", "clockTimer", "resumeTimer", "toastTimer", "bar", "pTitle", "pTime", "pFill", "loading", "barTimer", "seekTimer", "holdTimer", "keys", "panel", "chat", "chatLines", "chatTimer"]
        m[id] = m.top.findNode(id)
    end for
    m.data = invalid
    m.item = invalid      ' lo que se reproduce; invalid = en la portada
    m.onBri = false       ' foco en el brillo de la cabecera
    m.brightness = 100
    m.tasks = []
    m.keepId = ""

    m.rows.observeField("rowItemSelected", "onSelect")
    m.video.observeField("state", "onVideoState")
    m.video.observeField("position", "onPosition")
    m.panel.observeField("closed", "onPanelClosed")
    m.chatTimer.observeField("fire", "chatTick")
    m.chatOn = m.reg.Read("chat") <> "0"
    m.chatGen = 0
    m.muted = []
    m.refresh.observeField("fire", "onRefresh")
    m.retry.observeField("fire", "onRetry")
    m.clockTimer.observeField("fire", "drawClock")
    m.resumeTimer.observeField("fire", "saveResume")
    m.toastTimer.observeField("fire", "hideToast")
    m.barTimer.observeField("fire", "onBarTimer")
    m.seekTimer.observeField("fire", "applySeek")
    m.holdTimer.observeField("fire", "holdStep")
    m.target = -1
    m.holdDir = 0
    m.holdTicks = 0

    drawClock()
    setBrightness(100, false)
    m.clockTimer.control = "start"
    m.refresh.control = "start"
    m.rows.setFocus(true)
    loadHome("")
end sub

' ---------- red ----------
function api(path as string, body as dynamic, cb as string) as object
    t = CreateObject("roSGNode", "Api")
    t.url = m.server + path
    if body <> invalid then
        t.method = "POST"
        t.body = body
    end if
    if cb <> "" then t.observeField("result", cb)
    ' se guarda la referencia hasta que termine; las que ya pararon se sueltan
    alive = []
    for each old in m.tasks
        if old.state <> "stop" then alive.push(old)
    end for
    alive.push(t)
    m.tasks = alive
    t.control = "RUN"
    return t
end function

' ---------- portada ----------
sub loadHome(keepId as string)
    m.keepId = keepId
    api("/api/home", invalid, "onHome")
end sub

sub onHome(ev as object)
    r = ev.getData()
    if r.error <> invalid then
        m.msg.text = "No se pudo cargar la portada (" + r.error + "). Reintentando…"
        m.retry.control = "start"
        return
    end if
    m.data = r.data
    if m.data.brightness <> invalid then setBrightness(m.data.brightness, false)
    if m.item = invalid then render()
end sub

sub onRetry()
    loadHome(m.keepId)
end sub

sub onRefresh()
    if m.item = invalid and m.data <> invalid then loadHome(focusedId())
end sub

function itemNode(it as object) as object
    c = CreateObject("roSGNode", "ContentNode")
    if it.thumb <> invalid then
        u = m.server + "/img?u=" + it.thumb.EncodeUriComponent()
        ' la miniatura del directo cambia: se pide otra cada 5 min
        if it.kind = "live" then u = u + "&_=" + Int(nowSecs() / 300).ToStr()
        c.HDPosterUrl = u
    end if
    c.addFields({item: it})
    return c
end function

sub render()
    d = m.data
    root = CreateObject("roSGNode", "ContentNode")
    sizes = []
    heights = []
    for each sec in [{items: d.live, name: "En vivo ahora", size: [640, 360], h: 450}, {items: d.vods, name: "Anteriores", size: [400, 340], h: 400}, {items: d.discover, name: "También en vivo", size: [480, 270], h: 360}]
        if sec.items <> invalid and sec.items.count() > 0 then
            row = root.createChild("ContentNode")
            row.title = sec.name
            for each it in sec.items
                row.appendChild(itemNode(it))
            end for
            sizes.push(sec.size)
            heights.push(sec.h)
        end if
    end for
    m.msg.text = ""
    if d.errors <> invalid and d.errors.count() > 0 then
        txt = ""
        for each e in d.errors
            if txt <> "" then txt = txt + " · "
            txt = txt + e
        end for
        m.msg.text = "No se pudo consultar: " + txt
    else if root.getChildCount() = 0 then
        m.msg.text = "No sigues ningún canal con algo para ver. Pulsa * para buscar y agregar canales."
    end if
    if root.getChildCount() = 0 then
        m.rows.content = root  ' sin esto quedaban las tarjetas viejas y OK pedía un video que ya no existe
        return
    end if
    m.rows.rowItemSize = sizes
    m.rows.rowHeights = heights
    m.rows.content = root

    spot = [0, 0]  ' primer arranque: el directo si hay; si no, el anterior más reciente
    if m.keepId <> "" then
        for r = 0 to root.getChildCount() - 1
            row = root.getChild(r)
            for c = 0 to row.getChildCount() - 1
                if row.getChild(c).item.id = m.keepId then spot = [r, c]
            end for
        end for
    end if
    m.rows.jumpToRowItem = spot
end sub

function focusedId() as string
    f = m.rows.rowItemFocused
    if m.rows.content = invalid or f = invalid or f.count() < 2 then return ""
    row = m.rows.content.getChild(f[0])
    if row = invalid then return ""
    c = row.getChild(f[1])
    if c = invalid then return ""
    return c.item.id
end function

sub drawClock()
    d = CreateObject("roDateTime")
    d.ToLocalTime()
    h = d.GetHours()
    ap = "a. m."
    if h >= 12 then ap = "p. m."
    h12 = h mod 12
    if h12 = 0 then h12 = 12
    m.clock.text = h12.ToStr() + ":" + pad2(d.GetMinutes()) + " " + ap
end sub

' ---------- brillo ----------
sub setBrightness(v as integer, save as boolean)
    if v < 30 then v = 30
    if v > 100 then v = 100
    m.brightness = v
    m.dim.opacity = (100 - v) / 100.0
    hint = ""
    if m.onBri then hint = "< >  "
    m.bri.text = hint + "Brillo " + v.ToStr() + "%"
    if m.onBri then
        m.bri.color = "0xFFFFFFFF"
    else
        m.bri.color = "0x888888FF"
    end if
    if save then api("/api/state", {brightness: v}, "")
end sub

' ---------- reproductor ----------
function quality() as integer
    q = m.reg.Read("q")
    if q = "720" or q = "1080" then return q.ToInt()
    if m.data <> invalid and m.data.default_quality = 720 then return 720
    return 1080
end function

sub onSelect(ev as object)
    rc = ev.getData()
    c = m.rows.content.getChild(rc[0]).getChild(rc[1])
    openPlayer(c.item)
end sub

sub openPlayer(it as object)
    m.item = it
    m.started = false
    m.target = -1
    m.holdDir = 0
    m.pTitle.text = cleanText(it.channel + " · " + it.title)
    m.muted = []
    if it.platform = "twitch" and it.kind = "vod" then api("/api/muted/" + it.id, invalid, "onMuted")
    m.home.visible = false
    m.video.visible = true
    ' las teclas las maneja la escena: el avance nativo del Roku es muy lento en videos de horas
    m.keys.setFocus(true)
    start_(resumeOf(it))
    m.resumeTimer.control = "start"
    chatReset()
    m.chat.visible = m.chatOn
    layoutVideo()
    m.chatTimer.control = "start"
    showBar()
end sub

function resumeOf(it as object) as integer
    if it.kind = "vod" and it.resume_s <> invalid then return it.resume_s
    return 0
end function

sub start_(spot as integer)
    m.perr.visible = false
    c = CreateObject("roSGNode", "ContentNode")
    c.url = m.server + "/play/" + m.item.id + ".m3u8?q=" + quality().ToStr()
    c.streamFormat = "hls"
    c.title = m.item.channel + " · " + m.item.title
    c.live = (m.item.kind = "live")
    c.PlayStart = spot
    ' el directo de Kick redirige a su CDN por https
    c.HttpCertificatesFile = "common:/certs/ca-bundle.crt"
    m.video.content = c
    m.video.control = "play"
end sub

sub onVideoState(ev as object)
    s = ev.getData()
    if m.item = invalid then return
    m.loading.visible = (s = "buffering")
    if s = "playing" then
        m.started = true
        m.perr.visible = false
        showBar()
    else if s = "paused" then
        showBar()
    else if s = "error" then
        m.perr.text = "No se pudo reproducir (código " + m.video.errorCode.ToStr() + ": " + m.video.errorMsg + ")." + Chr(10) + "Atrás para volver."
        m.perr.visible = true
    else if s = "finished" then
        closePlayer()
    end if
end sub

' Devuelve la tarea del POST (o invalid si no hay nada que guardar).
function saveResume() as dynamic
    if m.item = invalid then return invalid
    if m.item.kind <> "vod" or not m.started then return invalid
    dur = m.item.duration_s
    if dur = invalid then dur = Int(m.video.duration)
    return api("/api/resume", {id: m.item.id, position_s: Int(m.video.position), duration_s: dur}, "")
end function

sub closePlayer()
    m.resumeTimer.control = "stop"
    id = m.item.id
    t = saveResume()
    m.item = invalid
    m.holdTimer.control = "stop"
    m.seekTimer.control = "stop"
    m.chatTimer.control = "stop"
    m.chat.visible = false
    m.video.width = 1920
    m.video.height = 1080
    m.video.translation = [0, 0]
    m.video.control = "stop"
    m.video.content = invalid
    m.video.visible = false
    m.perr.visible = false
    m.bar.visible = false
    m.loading.visible = false
    m.home.visible = true
    m.rows.setFocus(true)
    ' la barra roja de retomar se actualiza cuando el servidor ya guardó la posición
    if t = invalid then
        loadHome(id)
    else
        m.keepId = id
        t.observeField("result", "onSaved")
    end if
end sub

sub onSaved()
    loadHome(m.keepId)
end sub

sub toggleQuality()
    spot = 0
    if m.item.kind = "vod" then
        if m.target >= 0 then
            spot = Int(m.target)
        else if m.started then
            spot = Int(m.video.position)
        else
            spot = resumeOf(m.item)
        end if
    end if
    m.target = -1
    if quality() = 1080 then m.reg.Write("q", "720") else m.reg.Write("q", "1080")
    m.reg.Flush()
    m.started = false
    showToast(quality().ToStr() + "p")
    start_(spot)
end sub

sub showToast(text as string)
    m.toast.text = text
    m.toast.visible = true
    m.toastTimer.control = "stop"
    m.toastTimer.control = "start"
end sub

sub hideToast()
    m.toast.visible = false
end sub

' ---------- barra y avance propios ----------
function curTime() as float
    if m.target >= 0 then return m.target
    return m.video.position
end function

function curDuration() as float
    d = m.video.duration
    if d <> invalid and d > 0 then return d
    if m.item.duration_s <> invalid then return m.item.duration_s
    return 0
end function

sub showBar()
    if m.item = invalid then return
    m.bar.visible = true
    drawBar()
    m.barTimer.control = "stop"
    m.barTimer.control = "start"
end sub

sub onBarTimer()
    if m.item = invalid then return
    if m.video.state = "playing" and m.target < 0 and m.holdDir = 0 and mutedNote(m.video.position) = "" then
        m.bar.visible = false
    else
        m.barTimer.control = "start"
    end if
end sub

sub drawBar()
    q = quality().ToStr() + "p"
    paused = ""
    if m.video.state = "paused" then paused = " · en pausa"
    if m.item.kind = "live" then
        m.pTime.text = "EN VIVO · " + q + paused + "      OK chat  ·  ⏯ pausa  ·  ↺ calidad"
        m.pFill.width = 1760
        return
    end if
    t = curTime()
    d = curDuration()
    m.pTime.text = hms(t) + " / " + hms(d) + " · " + q + paused + mutedNote(t) + "      OK chat  ·  ⏯ pausa  ·  ↺ calidad"
    if d > 0 then m.pFill.width = 1760 * t / d else m.pFill.width = 0
end sub

sub onMuted(ev as object)
    r = ev.getData()
    if m.item = invalid or r.data = invalid or r.data.ranges = invalid then return
    m.muted = r.data.ranges
    drawBar()
end sub

' La barra se mantiene al día y aparece sola al entrar en un tramo silenciado.
sub onPosition()
    if m.item = invalid or m.item.kind <> "vod" then return
    if m.bar.visible then
        drawBar()
    else if mutedNote(m.video.position) <> "" then
        showBar()
    end if
end sub

' Twitch silencia tramos con música con derechos: sin aviso parecería que se dañó el audio.
function mutedNote(t as float) as string
    for each rg in m.muted
        if t >= rg[0] and t < rg[1] then return " · Twitch silenció este tramo hasta " + hms(rg[1])
    end for
    return ""
end function

' Acumula el destino y salta 0,4 s después de la última tecla, como en la TV.
sub seekBy(delta as float)
    if m.item.kind <> "vod" or not m.started then return
    t = curTime() + delta
    if t < 0 then t = 0
    d = curDuration()
    if d > 0 and t > d - 5 then t = d - 5
    m.target = t
    showBar()
    m.seekTimer.control = "stop"
    m.seekTimer.control = "start"
end sub

sub applySeek()
    if m.item = invalid or m.target < 0 or m.holdDir <> 0 then return
    m.video.seek = m.target
    m.target = -1
    drawBar()
end sub

' Mantener ← → acelera: 10 s, luego 30 s, 1 min y 5 min por paso (8 h se recorren en ~20 s).
sub holdStep()
    m.holdTicks = m.holdTicks + 1
    n = m.holdTicks
    jump = 10
    if n > 40 then
        jump = 300
    else if n > 20 then
        jump = 60
    else if n > 6 then
        jump = 30
    end if
    seekBy(m.holdDir * jump)
end sub

sub togglePause()
    if m.video.state = "paused" then m.video.control = "resume" else m.video.control = "pause"
    showBar()
end sub

function playerKey(key as string, press as boolean) as boolean
    if key = "left" or key = "right" then
        dir = 1
        if key = "left" then dir = -1
        if press then
            if m.holdDir = dir then return true  ' repetición del mismo botón mantenido
            m.holdDir = dir
            m.holdTicks = 0
            holdStep()
            m.holdTimer.control = "start"
        else
            m.holdTimer.control = "stop"
            m.holdDir = 0
            m.seekTimer.control = "stop"
            m.seekTimer.control = "start"
        end if
        return true
    end if
    if not press then return true
    if key = "back" then
        closePlayer()
    else if key = "play" then
        togglePause()
    else if key = "OK" then
        toggleChat()  ' el * no sirve: durante un video el Roku lo toma para su propio menú de opciones
    else if key = "fastforward" or key = "rewind" then
        if key = "fastforward" then seekBy(600) else seekBy(-600)
    else if key = "up" or key = "down" then
        if key = "up" then setBrightness(m.brightness + 10, true) else setBrightness(m.brightness - 10, true)
        showToast("Brillo " + m.brightness.ToStr() + "%")
    else if key = "replay" then
        toggleQuality()
    else
        showBar()
    end if
    return true
end function

' ---------- chat de solo lectura (misma lógica que TVL.chat* del front de la TV) ----------
sub chatReset()
    m.cs = {shown: [], buf: [], ids: {}, lastIds: [], until: -1, last: -1}
    m.chatGen = m.chatGen + 1
    m.chatBusy = false
    m.chatN = 0
    m.chatLines.removeChildrenIndex(m.chatLines.getChildCount(), 0)
end sub

sub chatKeep()
    while m.cs.shown.count() > 40
        m.cs.shown.shift()
    end while
    if m.cs.ids.Count() <= 500 then return
    ' en un directo de horas los ids crecían sin tope: basta con lo visible, lo pendiente y la última respuesta
    ids = {}
    for each msg in m.cs.shown
        ids[msg.id] = true
    end for
    for each msg in m.cs.buf
        ids[msg.id] = true
    end for
    for each id in m.cs.lastIds
        ids[id] = true
    end for
    m.cs.ids = ids
end sub

' Del más nuevo hacia arriba, hasta llenar 720 px del panel.
sub drawChat()
    m.chatLines.removeChildrenIndex(m.chatLines.getChildCount(), 0)
    s = m.cs.shown
    bottom = 720
    i = s.count() - 1
    while i >= 0 and bottom > 0
        line = CreateObject("roSGNode", "ChatLine")
        line.msg = s[i]
        bottom = bottom - line.height - 10
        if bottom < 0 then exit while
        line.translation = [0, bottom]
        m.chatLines.appendChild(line)
        i = i - 1
    end while
end sub

function chatDue(spot as float) as integer
    n = 0
    rest = []
    for each msg in m.cs.buf
        if msg.at <= spot then
            m.cs.shown.push(msg)
            n = n + 1
        else
            rest.push(msg)
        end if
    end for
    m.cs.buf = rest
    m.cs.last = spot
    chatKeep()
    return n
end function

sub chatTick()
    if m.item = invalid or not m.chatOn or m.chatBusy then return
    from = 0
    if m.item.kind = "live" then
        m.chatN = m.chatN + 1
        if m.chatN mod 3 <> 0 then return  ' en vivo, cada 3 s
    else
        if not m.started then return
        spot = curTime()
        ' un salto deja el chat de otra hora: se reinicia
        if (m.cs.last >= 0 and spot < m.cs.last - 3) or (m.cs.until >= 0 and spot > m.cs.until + 40) then chatReset()
        if chatDue(spot) > 0 then drawChat()
        if m.cs.until >= 0 and spot + 8 < m.cs.until then return
        if m.cs.until >= 0 then from = m.cs.until else from = Int(spot)
    end if
    m.chatBusy = true
    api("/api/chat/" + m.item.id + "?t=" + Int(from).ToStr(), invalid, "onChat")
    m.chatAsk = {gen: m.chatGen, id: m.item.id}
end sub

sub onChat(ev as object)
    r = ev.getData()
    if m.item = invalid or m.chatAsk = invalid then return
    if m.chatAsk.gen <> m.chatGen or m.chatAsk.id <> m.item.id then return  ' respuesta vieja
    m.chatBusy = false
    if r.error <> invalid or r.data = invalid or r.data.messages = invalid then return  ' el chat nunca molesta al video
    added = 0
    m.cs.lastIds = []
    for each msg in r.data.messages
        m.cs.lastIds.push(msg.id)
    end for
    for each msg in r.data.messages
        if m.cs.ids[msg.id] = invalid then
            m.cs.ids[msg.id] = true
            if m.item.kind = "live" then
                m.cs.shown.push(msg)
                added = added + 1
            else
                m.cs.buf.push(msg)
            end if
        end if
    end for
    if m.item.kind <> "live" and r.data.until <> invalid and r.data.until > m.cs.until then m.cs.until = r.data.until
    chatKeep()
    if added > 0 then drawChat()
end sub

' Con el chat visible el video ocupa 1380 px a la izquierda (16:9, centrado en alto); sin chat, la pantalla entera.
sub layoutVideo()
    if m.chatOn and m.item <> invalid then
        m.video.width = 1380
        m.video.height = 776
        m.video.translation = [0, 152]
    else
        m.video.width = 1920
        m.video.height = 1080
        m.video.translation = [0, 0]
    end if
end sub

sub toggleChat()
    m.chatOn = not m.chatOn
    if m.chatOn then m.reg.Write("chat", "1") else m.reg.Write("chat", "0")
    m.reg.Flush()
    chatReset()
    m.chat.visible = m.chatOn
    layoutVideo()
    if m.chatOn then showToast("Chat visible") else showToast("Chat oculto")
end sub

' ---------- panel de canales ----------
sub openPanel()
    m.onBri = false
    setBrightness(m.brightness, false)
    chans = m.data.channels
    if chans = invalid then chans = []
    m.panel.visible = true
    m.panel.channels = chans
end sub

sub onPanelClosed()
    m.panel.visible = false
    m.rows.setFocus(true)
    if m.panel.changed then loadHome(focusedId())
end sub

' ---------- teclado ----------
function onKeyEvent(key as string, press as boolean) as boolean
    if m.panel.visible then return true  ' el panel maneja sus teclas; las que suben no tocan la portada
    if m.item <> invalid then return playerKey(key, press)
    if not press then return false
    if key = "options" and m.data <> invalid then
        openPanel()
        return true
    end if
    ' portada: Arriba desde la primera fila sube al brillo, como el sol de la TV
    if m.onBri then
        if key = "left" or key = "right" then
            if key = "right" then setBrightness(m.brightness + 10, true) else setBrightness(m.brightness - 10, true)
            return true
        else if key = "down" or key = "back" then
            m.onBri = false
            setBrightness(m.brightness, false)
            m.rows.setFocus(true)
            return true
        end if
        return true
    end if
    if key = "up" then
        m.onBri = true
        m.keys.setFocus(true)
        setBrightness(m.brightness, false)
        return true
    end if
    return false
end function
