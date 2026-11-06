// name: Classic Spectrum Analyzer
// category: Bars
vec4 render() {
    vec2 uv = UV();
    float n = 32., segs = 26.;
    float x = (floor(uv.x * n) + .5) / n;
    float cx = fract(uv.x * n);
    float y = (uv.y - .05) / .9;
    float seg = floor(y * segs);
    float cy = fract(y * segs);
    float inside = step(.1, cx) * step(cx, .9) * step(.18, cy) * step(0., y) * step(y, 1.);
    float v = spec(x), pk = peak(x);
    float lit = step(seg / segs, v - .5 / segs);
    float pkSeg = step(abs(seg - floor(pk * segs)), .5) * step(.04, pk);
    vec3 col = seg / segs < .6 ? uC1 : seg / segs < .82 ? uC2 : uC3;
    float on = max(lit, pkSeg);
    float dim = .07;
    return vec4(col * inside * mix(dim, 1., on), inside * mix(.35, 1., on));
}
