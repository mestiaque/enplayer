// name: Circular Spectrum EQ
// category: Circular
vec4 render() {
    vec2 p = P();
    float r = length(p), a = atan(p.x, p.y);   // angle from the top: bass at the top, mirrored left/right
    float t = abs(a) / PI;                       // mirrored left/right
    float bars = 90.;
    float id = (floor(t * bars) + .5) / bars;
    float v = spec(id * .92 + .02);
    float r0 = .19 + .035 * uBass * uMotion + .02 * uBeat * uMotion;
    float len = .02 + v * .3;
    float cell = fract(t * bars);
    float mask = smoothstep(0., .18, cell) * smoothstep(1., .82, cell);
    float bar = step(r0, r) * step(r, r0 + len) * mask;
    float halo = exp(-max(r - r0 - len, 0.) * 22. / uGlow) * step(r0, r) * mask * v;
    float ring = glow(r - r0 + .012, .004);
    vec3 col = pal(id + uTime * .03);
    vec3 c = col * bar + col * halo * .7 + pal(.5) * ring;
    return vec4(c, bar + halo * .7 + ring);
}
