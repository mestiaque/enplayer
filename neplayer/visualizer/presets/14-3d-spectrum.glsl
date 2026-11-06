// name: 3D Spectrum
// category: Bars
vec4 render() {
    vec2 uv = UV();
    const int ROWS = 40;
    for (int k = 0; k < ROWS; k++) {                 // front (now) to back (older)
        float z = float(k) / float(ROWS);
        float persp = 1. - z * .55;
        float x = (uv.x - .5) / persp + .5;
        if (x < 0. || x > 1.) continue;
        float base = .1 + pow(z, .85) * .62;
        float h = hist(x, z) * .22 * persp;
        float y = base + h;
        if (uv.y < y) {                              // occluded by this ridge
            float d = (y - uv.y) * uRes.y;
            float lc = smoothstep(2., 0., d) + exp(-d / (5. * uGlow)) * .4;
            vec3 col = pal(z * .8 + x * .3 + uTime * .02) * (1. - z * .6);
            return vec4(col * lc, max(lc, .9));       // ridge line + solid fill hides rows behind
        }
    }
    return vec4(0.);
}
