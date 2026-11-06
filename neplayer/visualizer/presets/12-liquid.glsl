// name: Fluid / Liquid
// category: Abstract
vec4 render() {
    vec2 p = P() * 1.6;
    float t = uTime * .15 * uMotion;
    vec2 q = vec2(fbm(p + t), fbm(p + vec2(5.2, 1.3) - t));
    vec2 r = vec2(fbm(p + 3. * q * (.6 + uMid) + vec2(1.7, 9.2) + .5 * uBass),
                  fbm(p + 3. * q + vec2(8.3, 2.8) + t));
    float f = fbm(p + 3.5 * r);
    vec3 col = mix(uC1, uC2, clamp(f * f * 3., 0., 1.));
    col = mix(col, uC3, clamp(length(q) * (.6 + uTreble), 0., 1.));
    // deep troughs and bright crests so the liquid reads even with close theme colours
    float shade = smoothstep(.25, .85, f);
    col = mix(col * .12, col * (1.2 + .6 * uBass), shade);
    col += pow(max(f - .62, 0.), 2.) * 6. * uC3 * (1. + uBeat * uMotion);
    return vec4(col, 1.);
}
