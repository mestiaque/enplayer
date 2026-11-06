// name: Mirrored Equalizer
// category: Bars
vec4 render() {
    vec2 uv = UV();
    float n = 80.;
    float cell = fract(uv.x * n);
    float x = (floor(uv.x * n) + .5) / n;
    float v = spec(abs(x - .5) * 2.) * .46 + .004;   // bass in the middle
    float d = abs(uv.y - .5);
    float gap = step(.16, cell) * step(cell, .84);
    float bar = step(d, v) * gap;
    vec3 col = pal(abs(x - .5) * 1.6 + uTime * .02);
    float fade = mix(1., .45, d / max(v, 1e-3));
    float center = glow(uv.y - .5, .003) * .6;
    float aura = exp(-max(d - v, 0.) * 40. / uGlow) * gap * v * 1.5;
    return vec4(col * (bar * fade + aura) + pal(.5) * center, bar + aura + center);
}
