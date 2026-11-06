// name: Polygon Ring
// category: Circular
vec4 render() {
    vec2 p = P();
    float dmin = 1e9;
    const int N = 48;
    vec2 prev, first;
    for (int i = 0; i <= N; i++) {
        float t = float(i) / float(N);
        float ang = t * TAU + uTime * .1 * uMotion;
        float e = spec(abs(fract(t) * 2. - 1.) * .9);
        float R = .24 + e * .14 + hash(vec2(float(i), 1.)) * .015;
        vec2 q = R * vec2(cos(ang), sin(ang));
        if (i > 0) dmin = min(dmin, sdSeg(p, prev, q));
        // spokes to an inner ring give the low-poly look
        vec2 inner = .2 * vec2(cos(ang + .065), sin(ang + .065));
        dmin = min(dmin, sdSeg(p, q, inner));
        prev = q;
    }
    float s = line(dmin, 1.6 * px()) + glow(dmin, .008) * .6;
    float r = length(p);
    vec3 col = pal(r * 2. + uTime * .03);
    float shards = 0.;
    vec2 g = p * 6.;
    vec2 cell = floor(g);
    float h = hash(cell);
    if (h > .82) shards = smoothstep(.2, .15, length(fract(g) - .5 + (hash2(cell) - .5) * .4)) * .25 * (.5 + uBass);
    return vec4(col * s + uC1 * shards, s + shards);
}
