// name: Dual Channel Stereo Spectrum
// category: Bars
vec4 render() {
    vec2 uv = UV();
    float half_ = uv.x < .5 ? 0. : 1.;
    float x = half_ < .5 ? (.5 - uv.x) * 2. : (uv.x - .5) * 2.;   // bass at the centre
    float n = 48.;
    float cell = fract(x * n);
    float xi = (floor(x * n) + .5) / n;
    float v = half_ < .5 ? specL(xi) : specR(xi);
    float y = (uv.y - .06) / .86;
    float gap = step(.14, cell) * step(cell, .86);
    float bar = step(0., y) * step(y, v) * gap;
    vec3 col = mix(half_ < .5 ? uC1 : uC3, uC2, y);
    float divider = line(uv.x - .5, .0015) * .5;
    float label = 0.;
    return vec4(col * bar + vec3(divider), bar + divider + label);
}
