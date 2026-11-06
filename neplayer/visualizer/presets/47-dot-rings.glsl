// name: Dot Rings
// category: Circular
vec4 render() {
    vec2 p = P();
    float r = length(p), a = atan(p.y, p.x);
    vec3 c = vec3(0); float al = 0.;
    for (int i = 0; i < 9; i++) {
        float fi = float(i);
        float R = .08 + fi * .045;
        float e = spec(fi / 9. * .9 + .03);
        float count = 12. + fi * 8.;
        float ang = a + uTime * (.1 + fi * .02) * uMotion * (mod(fi, 2.) < .5 ? 1. : -1.);
        float k = floor(ang / TAU * count + .5);
        float ca = k / count * TAU;
        vec2 dotc = R * vec2(cos(ca), sin(ca));
        vec2 q = r * vec2(cos(ang), sin(ang));
        float size = .004 + e * .009;
        float d = length(q - dotc);
        float s = smoothstep(size, size * .4, d) + glow(d, .004) * e * .6;
        c += pal(fi / 9. + uTime * .02) * s * (.4 + e * 1.4);
        al += s;
    }
    return vec4(c, al);
}
