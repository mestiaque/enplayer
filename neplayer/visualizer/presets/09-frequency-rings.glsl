// name: Frequency Rings
// category: Circular
vec4 render() {
    vec2 p = P();
    float r = length(p);
    vec3 c = vec3(0); float a = 0.;
    const int N = 14;
    for (int i = 0; i < N; i++) {
        float f = float(i) / float(N);
        float e = spec(f * .95 + .02);
        float R = .04 + f * .42 + e * .025 * uMotion;
        float w = .002 + e * .01;
        float g = line(r - R, w) + glow(r - R, .004 + e * .012) * e;
        c += pal(f + uTime * .02) * g * (.25 + e);
        a += g * (.25 + e);
    }
    return vec4(c, a);
}
