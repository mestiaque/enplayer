// name: Equalizer Skyline
// category: Bars
vec4 render() {
    vec2 uv = UV();
    float n = 34.;
    float cx = floor(uv.x * n);
    float x = (cx + .5) / n;
    float cell = fract(uv.x * n);
    float hb = .12 + hash(vec2(cx, 7.)) * .12;
    float h = hb + spec(x) * .55;
    float building = step(uv.y, h) * step(.06, cell) * step(cell, .94);
    vec2 win = fract(vec2(cell * 4., uv.y * 60.));
    float lit = step(.35, win.x) * step(win.x, .75) * step(.4, win.y) * step(win.y, .8);
    float on = step(hash(vec2(cx, floor(uv.y * 60.))), .3 + spec(x));
    vec3 body = mix(vec3(.03, .03, .06), uC1 * .25, uv.y / max(h, .01));
    vec3 col = body + pal(x) * lit * on * building * 1.2;
    float roof = line(uv.y - h, .002) * step(.06, cell) * step(cell, .94);
    float sky = smoothstep(.9, .2, uv.y) * .25;
    return vec4(col * building + pal(x) * roof + uC2 * sky * (1. - building), max(building, sky + roof));
}
