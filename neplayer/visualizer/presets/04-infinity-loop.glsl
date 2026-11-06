// name: Infinity Loop
// category: Circular
vec4 render() {
    vec2 p = P();
    float sc = .62 + .06 * uBass * uMotion;
    float dmin = 1e9, tmin = 0.;
    vec2 prev = vec2(0);
    const int N = 150;
    for (int i = 0; i <= N; i++) {
        float t = float(i) / float(N) * TAU + uTime * .2 * uMotion;
        float s = sin(t), c = cos(t), den = 1. + s * s;
        vec2 q = vec2(c / den, s * c / den) * sc;
        float f = spec(abs(fract(float(i) / float(N)) * 2. - 1.) * .85);
        q *= 1. + f * .22;
        if (i > 0) {
            float d = sdSeg(p, prev, q);
            if (d < dmin) { dmin = d; tmin = float(i) / float(N); }
        }
        prev = q;
    }
    float core = line(dmin, 2.5 * px());
    float g = glow(dmin, .02);
    vec3 col = pal(tmin * 2. + uTime * .05);
    return vec4(col * (core + g * .8) + vec3(1.) * core * .4, core + g * .8);
}
