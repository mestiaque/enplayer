// name: Circular Waveform
// category: Circular
vec4 render() {
    vec2 p = P();
    float r = length(p), a = atan(p.y, p.x);
    float t = a / TAU + .5;
    float base = .26 + .04 * uBass * uMotion;
    float amp = .09 * (.5 + uLevel);
    // blend the seam so the ring closes smoothly
    float wl = mix(waveL(t), waveL(1. - t), smoothstep(.9, 1., t));
    float wr = mix(waveR(t), waveR(1. - t), smoothstep(.9, 1., t));
    float d1 = r - (base + wl * amp), d2 = r - (base * .78 + wr * amp * .8);
    float c1 = line(d1, 2. * px()) + glow(d1, .012) * .7;
    float c2 = line(d2, 2. * px()) + glow(d2, .01) * .5;
    return vec4(pal(t + uTime * .04) * c1 + uC3 * c2, c1 + c2);
}
