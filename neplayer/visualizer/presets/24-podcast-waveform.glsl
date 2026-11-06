// name: Podcast Waveform
// category: Waveform
vec4 render() {
    vec2 uv = UV();
    float n = 120.;
    float cell = fract(uv.x * n);
    float x = (floor(uv.x * n) + .5) / n;
    float env = smoothstep(0., .35, x) * smoothstep(1., .65, x);
    float v = (.012 + abs(wave(x)) * .22 * (.4 + uLevel) + spec(abs(x - .5) * 1.4) * .08) * env;
    float d = abs(uv.y - .5);
    float bar = step(d, v) * step(.3, cell) * step(cell, .7);
    vec3 col = mix(uC1, uC3, x);
    return vec4(col * bar, bar);
}
