sub init()
    for each id in ["ph", "thumb", "shade", "badge", "durBg", "dur", "prog", "plat", "platName", "l1", "l2", "l3"]
        m[id] = m.top.findNode(id)
    end for
end sub

sub place(node as object, x as float, y as float, w as float, h as float)
    node.translation = [x, y]
    node.width = w
    if h > 0 then node.height = h
end sub

sub show()
    c = m.top.itemContent
    if c = invalid or c.item = invalid then return
    it = c.item
    w = m.top.width
    m.thumb.uri = c.HDPosterUrl
    m.plat.visible = false  ' solo hay Twitch: la etiqueta de plataforma ya no dice nada

    if it.kind = "live" then
        h = m.top.height
        place(m.ph, 0, 0, w, h)
        place(m.thumb, 0, 0, w, h)
        place(m.shade, 0, h - 170, w, 170)
        m.shade.visible = true
        m.badge.visible = true
        m.durBg.visible = false
        m.prog.visible = false
        place(m.l1, 20, h - 160, w - 40, 40)
        m.l1.text = cleanText(nameOf(it))
        place(m.l2, 20, h - 115, w - 40, 0)
        m.l2.maxLines = 1
        m.l2.text = cleanText(it.title)
        place(m.l3, 20, h - 60, w - 40, 40)
        started = ""
        if it.started_at <> invalid then started = since(it.started_at)
        m.l3.text = cleanText(joinDot([viewers(it.viewers), it.category, started]))
    else
        th = Int(w * 9 / 16)
        place(m.ph, 0, 0, w, th)
        place(m.thumb, 0, 0, w, th)
        m.shade.visible = false
        m.badge.visible = false
        m.durBg.visible = true
        m.durBg.translation = [w - 140, th - 46]
        m.dur.text = hms(it.duration_s)
        ratio = 0
        if it.resume_s <> invalid and it.duration_s <> invalid then
            if it.duration_s > 0 then ratio = it.resume_s / it.duration_s
        end if
        if ratio > 1 then ratio = 1
        m.prog.visible = ratio > 0
        place(m.prog, 0, th - 6, w * ratio, 6)
        place(m.l2, 0, th + 10, w, 0)
        m.l2.maxLines = 2
        m.l2.text = cleanText(it.title)
        m.l1.text = ""
        place(m.l3, 0, th + 95, w, 30)
        m.l3.text = cleanText(nameOf(it)) + " · " + relDay(it.started_at)
    end if
end sub
