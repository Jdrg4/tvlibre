sub init()
    m.server = CreateObject("roAppInfo").GetValue("tvlibre_server")
    m.list = m.top.findNode("list")
    m.subtitle = m.top.findNode("sub")
    m.msg = m.top.findNode("msg")
    m.items = []
    m.tasks = []
    m.list.observeField("itemSelected", "onPick")
end sub

' La portada pasa sus canales al abrir: se muestran como "Tus canales".
sub open()
    m.items = []
    for each c in m.top.channels
        m.items.push({platform: c.platform, slug: c.slug, name: c.slug, live: false, following: true})
    end for
    m.top.changed = false
    m.subtitle.text = "Tus canales"
    m.msg.text = ""
    draw(0)
    m.list.setFocus(true)
end sub

sub draw(focusAt as integer)
    root = CreateObject("roSGNode", "ContentNode")
    first = root.createChild("ContentNode")
    first.title = "Buscar en Kick y Twitch…"
    for each it in m.items
        line = cleanText(it.name) + "  ·  " + UCase(it.platform)
        if it.live then line = line + "  ·  EN VIVO"
        if it.following then line = line + "      [ Siguiendo ]" else line = line + "      [ Seguir ]"
        root.createChild("ContentNode").title = line
    end for
    m.list.content = root
    if focusAt > m.items.count() then focusAt = 0
    m.list.jumpToItem = focusAt
end sub

function request(path as string, body as dynamic, cb as string) as object
    t = CreateObject("roSGNode", "Api")
    t.url = m.server + path
    if body <> invalid then
        t.method = "POST"
        t.body = body
    end if
    t.observeField("result", cb)
    m.tasks.push(t)  ' la referencia evita que la tarea muera antes de responder
    if m.tasks.count() > 8 then m.tasks.shift()
    t.control = "RUN"
    return t
end function

sub onPick()
    i = m.list.itemSelected
    if i = 0 then
        askText()
    else
        toggle(i - 1)
    end if
end sub

sub askText()
    d = CreateObject("roSGNode", "StandardKeyboardDialog")
    d.title = "Buscar canal"
    d.buttons = ["Buscar", "Cancelar"]
    d.observeField("buttonSelected", "onDialog")
    d.observeField("wasClosed", "onDialogClosed")
    m.dialog = d
    m.top.getScene().dialog = d
end sub

sub onDialog()
    d = m.dialog
    text = d.text.Trim()
    d.close = true
    if d.buttonSelected <> 0 or text = "" then return
    if Len(text) > 40 then text = Left(text, 40)
    m.subtitle.text = "Buscando " + Chr(34) + text + Chr(34) + "…"
    m.query = text
    request("/api/search?q=" + text.EncodeUriComponent(), invalid, "onResults")
end sub

sub onDialogClosed()
    m.list.setFocus(true)
end sub

sub onResults(ev as object)
    r = ev.getData()
    if r.error <> invalid then
        m.msg.text = "No se pudo buscar (" + r.error + ")."
        return
    end if
    m.items = r.data.results
    m.subtitle.text = "Resultados de " + Chr(34) + m.query + Chr(34)
    m.msg.text = ""
    if r.data.errors.count() > 0 then m.msg.text = "No respondió: " + r.data.errors[0]
    if m.items.count() = 0 then m.subtitle.text = m.subtitle.text + ": nada"
    draw(1)
end sub

sub toggle(i as integer)
    if i >= m.items.count() then return
    it = m.items[i]
    m.pending = i
    request("/api/channels", {platform: it.platform, slug: it.slug, follow: not it.following}, "onSaved")
end sub

sub onSaved(ev as object)
    r = ev.getData()
    if r.error <> invalid then
        m.msg.text = "No se pudo guardar (" + r.error + ")."
        return
    end if
    m.items[m.pending].following = not m.items[m.pending].following
    m.top.changed = true
    m.msg.text = ""
    draw(m.pending + 1)
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if press and key = "back" then
        m.top.closed = true
        return true
    end if
    return false
end function
