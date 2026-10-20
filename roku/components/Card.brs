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
    if it.platform = "kick" then
        m.plat.color = "0x53FC18FF"
        m.platName.color = "0x000000FF"
    else
        m.plat.color = "0x9146FFFF"
        m.platName.color = "0xFFFFFFFF"
    end if
    m.platName.text = UCase(it.platform)

    if it.kind = "live" then
        h = m.top.height
        place(m.ph, 0, 0, w, h)
        place(m.thumb, 0, 0, w, h)
        place(m.shade, 0, h - 170, w, 170)
        m.shade.visible = true
        m.badge.visible = true
        m.durBg.visible = false
        m.prog.visible = false
        m.plat.translation = [20, h - 155]
        place(m.l1, 155, h - 160, w - 175, 40)
        m.l1.text = it.channel
        place(m.l2, 20, h - 115, w - 40, 0)
        m.l2.maxLines = 1
        m.l2.text = cleanText(it.title)
        place(m.l3, 20, h - 60, w - 40, 40)
        m.l3.text = viewers(it.viewers) + " · " + since(it.started_at)
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
        m.plat.translation = [0, th + 95]
        place(m.l3, 130, th + 95, w - 130, 30)
        m.l3.text = it.channel + " · " + relDay(it.started_at)
    end if
end sub
