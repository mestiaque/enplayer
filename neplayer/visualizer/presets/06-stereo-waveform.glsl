// name: Stereo Waveform
// category: Waveform
float trace(float ys, float center, float amp, float sampleV, float sampleV2) {
    float y = center + sampleV * amp, y2 = center + sampleV2 * amp;
    float slope = (y2 - y) * uRes.y;
    return abs(ys - y) * uRes.y / sqrt(1. + slope * slope);
}
vec4 render() {
    vec2 uv = UV();
    float e = 1. / uRes.x, amp = .17 * (.6 + .6 * uLevel);
    float dl = trace(uv.y, .73, amp, waveL(uv.x), waveL(uv.x + e));
    float dr = trace(uv.y, .27, amp, waveR(uv.x), waveR(uv.x + e));
    float cl = smoothstep(2., 0., dl) + exp(-dl / (9. * uGlow)) * .6;
    float cr = smoothstep(2., 0., dr) + exp(-dr / (9. * uGlow)) * .6;
    float axis = line(uv.y - .5, .0015) * .25;
    return vec4(uC1 * cl + uC3 * cr + vec3(axis), cl + cr + axis);
}
