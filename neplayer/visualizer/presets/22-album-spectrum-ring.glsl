// name: Album Art Spectrum Ring
// category: Album art
vec4 render() {
    vec2 p = P();
    float r = length(p);
    float R = .17 + .02 * uBass * uMotion;
    float art = smoothstep(R + px(), R, r);
    vec3 col = coverAt(p / (R * 2.) + .5);
    float edge = line(r - R, .003);
    float t = abs(atan(p.x, p.y)) / PI;
    float bars = 72.;
    float cell = fract(t * bars);
    float id = (floor(t * bars) + .5) / bars;
    float v = spec(id * .9) * .2 + .01;
    float bar = step(R + .025, r) * step(r, R + .025 + v) * smoothstep(0., .2, cell) * smoothstep(1., .8, cell);
    float halo = glow(r - R - .025, .02) * uBass * .5;
    vec3 c = col * art + vec3(1.) * edge * .8 + pal(id + uTime * .02) * (bar + halo);
    return vec4(c, art + edge + bar + halo);
}
