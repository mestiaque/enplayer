// name: Square Pulse
// category: Abstract
vec4 render() {
    vec2 p = P();
    vec3 c = vec3(0); float a = 0.;
    for (int i = 0; i < 9; i++) {
        float fi = float(i);
        float e = spec(fi / 9. * .9 + .03);
        vec2 q = p * rot(uTime * (.1 + fi * .03) * uMotion * (mod(fi, 2.) < .5 ? 1. : -1.) + fi * .2);
        float s = .05 + fi * .045 + e * .03;
        float d = max(abs(q.x), abs(q.y)) - s;
        float l = line(d, .0025 + e * .004) + glow(d, .006) * e;
        c += pal(fi / 9. + uTime * .02) * l;
        a += l;
    }
    return vec4(c, a);
}
