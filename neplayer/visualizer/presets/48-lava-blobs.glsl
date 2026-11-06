// name: Lava Blobs
// category: Abstract
vec4 render() {
    vec2 p = P();
    float field = 0.;
    vec3 c = vec3(0);
    for (int i = 0; i < 7; i++) {
        float fi = float(i);
        float e = spec(.05 + fi * .13);
        vec2 ctr = .32 * vec2(sin(uTime * (.23 + fi * .05) * uMotion + fi * 1.7), cos(uTime * (.19 + fi * .04) * uMotion + fi * 2.3));
        float rad = .06 + e * .07;
        float f = rad * rad / max(dot(p - ctr, p - ctr), 1e-4);
        field += f;
        c += pal(fi / 7.) * f;
    }
    c /= max(field, 1e-3);
    float m = smoothstep(.9, 1.1, field);
    float rim = line(field - 1., .08) * .6;
    return vec4(c * m * (.7 + .3 * uLevel) + vec3(rim), m + rim);
}
