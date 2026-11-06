// name: Retro Neon Sun
// category: Retro
vec4 render() {
    vec2 p = P();
    float r = length(p);
    float R = .26 + .03 * uBass * uMotion;
    float sun = smoothstep(R + px(), R, r);
    float y = (p.y + R) / (2. * R);
    float gap = smoothstep(.0, .02, abs(fract(y * 8. + uTime * .25 * uMotion) - .5) - .12 * (1. - y));
    sun *= mix(1., gap, step(y, .55));
    vec3 col = mix(uC3, uC1, y);
    float halo = exp(-max(r - R, 0.) * 10.) * (.25 + .5 * uLevel);
    float t = (p.x / .9) + .5;
    float bars = step(.15, fract(t * 60.)) * step(p.y, -R * .3) * step(-R * .3 - spec(abs(t - .5) * 2.) * .25, p.y) * (1. - sun);
    return vec4(col * sun + uC2 * halo + uC2 * bars, sun + halo + bars);
}
