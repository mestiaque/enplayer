// name: Oscilloscope Waveform
// category: Waveform
vec4 render() {
    vec2 uv = UV();
    float amp = .32 * (.6 + .6 * uLevel);
    float y = .5 + wave(uv.x) * amp;
    float y2 = .5 + wave(uv.x + 1. / uRes.x) * amp;
    float slope = (y2 - y) * uRes.y;
    float d = abs(uv.y - y) * uRes.y / sqrt(1. + slope * slope);
    float core = smoothstep(2.2, 0., d);
    float g = exp(-d / (10. * uGlow));
    vec2 grid = abs(fract(uv * vec2(10., 6.)) - .5);
    float gr = (smoothstep(.49, .5, max(grid.x, grid.y))) * .08;
    vec3 col = pal(uv.x * .4 + uTime * .03);
    return vec4(col * (core + g * .6) + vec3(gr), core + g * .6 + gr);
}
