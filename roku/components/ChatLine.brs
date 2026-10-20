sub init()
    m.server = CreateObject("roAppInfo").GetValue("tvlibre_server")
end sub

' Ubica la pieza en (x, y) y salta de renglón si no cabe.
sub flow(node as object, w as float)
    if m.x > 0 and m.x + w > m.top.width then
        m.x = 0
        m.y = m.y + m.lineH
    end if
    node.translation = [m.x, m.y]
    m.x = m.x + w
    m.top.appendChild(node)
end sub

function word(text as string, bold as boolean, color as string) as object
    l = CreateObject("roSGNode", "Label")
    if bold then l.font = "font:SmallestBoldSystemFont" else l.font = "font:SmallestSystemFont"
    l.color = color
    l.text = text
    return l
end function

sub layout()
    m.top.removeChildrenIndex(m.top.getChildCount(), 0)
    msg = m.top.msg
    m.x = 0
    m.y = 0
    m.lineH = 34
    color = "0x9AA0FFFF"
    if msg.color <> invalid and Len(msg.color) = 7 then color = "0x" + Mid(msg.color, 2) + "FF"
    l = word(cleanText(msg.user) + ": ", true, color)
    flow(l, l.boundingRect().width)
    parts = msg.parts
    if parts = invalid then parts = [{t: msg.text}]
    for each p in parts
        if p.e <> invalid then
            img = CreateObject("roSGNode", "Poster")
            img.width = 30
            img.height = 30
            img.loadDisplayMode = "scaleToFit"
            img.uri = m.server + "/img?u=" + p.e.EncodeUriComponent()
            flow(img, 34)
        else if p.t <> invalid then
            for each raw in p.t.Split(" ")
                piece = cleanText(raw)
                if piece <> "" then
                    l = word(piece + " ", false, "0xEFEFF1FF")
                    w = l.boundingRect().width
                    if w > m.top.width then  ' una palabra eterna (un enlace) se corta con "…"
                        l.width = m.top.width
                        w = m.top.width
                    end if
                    flow(l, w)
                end if
            end for
        end if
    end for
    m.top.height = m.y + m.lineH
end sub
