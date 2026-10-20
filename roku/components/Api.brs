sub init()
    m.top.functionName = "run"
end sub

' Deja en result {data: ...} o {error: "..."}. Tope de 30 s, como el front de la TV.
sub run()
    port = CreateObject("roMessagePort")
    t = CreateObject("roUrlTransfer")
    t.SetMessagePort(port)
    t.SetUrl(m.top.url)
    if m.top.method = "POST" then
        t.AddHeader("Content-Type", "application/json")
        t.AsyncPostFromString(FormatJson(m.top.body))
    else
        t.AsyncGetToString()
    end if
    msg = wait(30000, port)
    if type(msg) <> "roUrlEvent" then
        t.AsyncCancel()
        m.top.result = {error: "sin conexión"}
        return
    end if
    code = msg.GetResponseCode()
    if code < 200 or code >= 300 then
        if code < 0 then
            m.top.result = {error: msg.GetFailureReason()}
        else
            m.top.result = {error: "HTTP " + code.ToStr()}
        end if
        return
    end if
    data = invalid
    body = msg.GetString()
    if body <> "" then data = ParseJson(body)  ' un 204 llega vacío
    if data = invalid then data = {}
    m.top.result = {data: data}
end sub
