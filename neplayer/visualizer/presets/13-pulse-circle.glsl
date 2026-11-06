// name: Pulse Circle
// category: Circular
vec4 render() {
    vec2 p = P();
    float r = length(p);
    float R = .1 + .14 * uBass * uMotion + .04 * uBeat * uMotion;
    float disc = smoothstep(R + px() * 2., R, r);
    float edge = glow(r - R, .01);
    float rip = 0.;
    for (int k = 0; k < 4; k++) {
        float ph = fract(uTime * .35 * uMotion + float(k) * .25);
        float rr = R + ph * .55;
        rip += line(r - rr, .002 + .004 * uLevel) * (1. - ph) * (.3 + uLevel);
    }
    float beatRing = line(r - (R + (1. - uBeat) * .45), .004) * uBeat;
    vec3 inner = mix(uC1, uC2, r / max(R, .01));
    return vec4(inner * disc + uC2 * edge + pal(r * 2. + uTime * .05) * rip + uC3 * beatRing,
                disc + edge + rip + beatRing);
}
