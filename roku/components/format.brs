' Textos de las tarjetas, iguales a los del front de la TV (tvlibre/web/app.js).

function pad2(n as integer) as string
    if n < 10 then return "0" + n.ToStr()
    return n.ToStr()
end function

' Quita lo que la fuente del Roku no dibuja (emojis y símbolos salen como cuadros).
function cleanText(s as dynamic) as string
    if s = invalid then return ""
    out = ""
    for i = 1 to Len(s)
        ch = Mid(s, i, 1)
        code = Asc(ch)
        if code < &h2000 or (code >= &h2010 and code <= &h206F) or code = &h20AC then out = out + ch
    end for
    while Instr(1, out, "  ") > 0
        out = out.Replace("  ", " ")
    end while
    return out.Trim()
end function

function hms(s as dynamic) as string
    if s = invalid then s = 0
    s = Int(s)
    if s < 0 then s = 0
    return Int(s / 3600).ToStr() + ":" + pad2(Int(s / 60) mod 60) + ":" + pad2(s mod 60)
end function

function isoSecs(iso as dynamic) as integer
    if iso = invalid then return 0
    d = CreateObject("roDateTime")
    d.FromISO8601String(iso)
    return d.AsSeconds()
end function

function nowSecs() as integer
    d = CreateObject("roDateTime")
    return d.AsSeconds()
end function

' Día local (no UTC) de un instante, para decir "hoy" y "ayer" bien de noche.
function localDay(secs as integer) as integer
    d = CreateObject("roDateTime")
    return Int((secs - d.GetTimeZoneOffset() * 60) / 86400)
end function

function relDay(iso as dynamic) as string
    days = localDay(nowSecs()) - localDay(isoSecs(iso))
    if days <= 0 then return "hoy"
    if days = 1 then return "ayer"
    return "hace " + days.ToStr() + " días"
end function

function since(iso as dynamic) as string
    mins = Int((nowSecs() - isoSecs(iso)) / 60)
    if mins < 0 then mins = 0
    if mins < 60 then return "hace " + mins.ToStr() + " min"
    return "hace " + Int(mins / 60).ToStr() + " h " + (mins mod 60).ToStr() + " min"
end function

function viewers(n as dynamic) as string
    if n = invalid then return ""
    if n >= 1000 then
        tenths = Int(n / 100 + 0.5)
        s = Int(tenths / 10).ToStr()
        if tenths mod 10 <> 0 then s = s + "," + (tenths mod 10).ToStr()
        return s + " mil espectadores"
    end if
    return n.ToStr() + " espectadores"
end function
