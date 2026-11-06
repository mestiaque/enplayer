// name: HUD Rings
// category: Sci-fi
vec4 render() {
    vec2 p = P();
    float r = length(p), a = atan(p.y, p.x);
    vec3 c = vec3(0); float al = 0.;
    for (int i = 0; i < 6; i++) {
        float fi = float(i);
        float R = .1 + fi * .055;
        float e = spec(.05 + fi * .15);
        float dir = mod(fi, 2.) < .5 ? 1. : -1.;
        float ang = a + dir * uTime * (.2 + .15 * fi) * uMotion;
        float segs = 6. + fi * 6.;
        float seg = step(.25 + .2 * sin(fi), fract(ang / TAU * segs));
        float ring = line(r - R, .0025 + e * .004) * seg;
        float ticks = line(r - R - .018, .007) * step(.85, fract(ang / TAU * 72.)) * (fi == 3. ? 1. : 0.);
        float s = (ring * (.4 + 1.6 * e) + ticks * .6);
        c += pal(fi / 6. + uTime * .02) * s;
        al += s;
    }
    float t = abs(atan(p.x, p.y)) / PI;
    float outer = .43;
    float bar = step(outer, r) * step(r, outer + spec(t) * .08) * step(.3, fract(t * 120.));
    float core = exp(-r * 14.) * (.5 + uBeat);
    return vec4(c + uC3 * bar + uC2 * core, al + bar + core);
}
