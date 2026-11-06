// name: Kaleidoscope
// category: Abstract
vec4 render() {
    vec2 p = P();
    float r = length(p), a = atan(p.y, p.x);
    float seg = 8.;
    a = mod(a, TAU / seg);
    a = abs(a - PI / seg);
    vec2 q = r * vec2(cos(a), sin(a));
    q *= rot(uTime * .1 * uMotion);
    float f = fbm(q * (3. + uMid * 2.) + uTime * .2 * uMotion);
    float g = fbm(q * 6. - uTime * .15 * uMotion + f);
    float e = spec(clamp(r * 1.4, 0., 1.));
    vec3 col = pal(f + g * .5 + r * .5) * (.25 + 1.4 * g * g + e);
    float mask = smoothstep(.5, .35, r);
    return vec4(col * mask, mask);
}
