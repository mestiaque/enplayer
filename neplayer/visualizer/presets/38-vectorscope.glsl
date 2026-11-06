// name: Stereo Vectorscope
// category: Waveform
vec4 render() {
    vec2 p = P();
    float dmin = 1e9;
    const int N = 160;
    vec2 prev = vec2(0);
    for (int i = 0; i < N; i++) {
        float t = float(i) / float(N);
        float l = waveL(t), r = waveR(t);
        vec2 q = vec2(l - r, l + r) * .7071 * .32;   // mid/side, rotated 45°
        if (i > 0) dmin = min(dmin, sdSeg(p, prev, q));
        prev = q;
    }
    float s = line(dmin, 1.5 * px()) + glow(dmin, .006) * .7;
    float axes = (line(p.x, px()) + line(p.y, px())) * .12 + line(length(p) - .42, px()) * .15;
    return vec4(uC2 * s + vec3(axes), s + axes);
}
