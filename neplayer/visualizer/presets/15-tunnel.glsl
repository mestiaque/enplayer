// name: Tunnel
// category: Abstract
vec4 render() {
    vec2 p = P();
    float r = length(p) + 1e-3, a = atan(p.y, p.x);
    float depth = .25 / r + uTime * (.5 + 1.6 * uLevel) * uMotion;
    float ang = a / TAU + .5;
    float e = spec(abs(ang * 2. - 1.) * .9);
    float rings = smoothstep(.45, .5, abs(fract(depth * 3.) - .5)) * (.4 + uBass);
    float spokes = smoothstep(.42, .5, abs(fract(ang * 24. + depth * .2) - .5)) * e;
    float fog = smoothstep(0., .5, r);
    vec3 col = pal(depth * .15 + ang) * (rings + spokes * 1.4) * fog;
    col += uC2 * exp(-r * 10.) * (.3 + uBeat);
    return vec4(col, clamp((rings + spokes) * fog + exp(-r * 10.) * .5, 0., 1.));
}
