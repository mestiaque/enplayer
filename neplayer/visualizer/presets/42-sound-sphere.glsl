// name: Sound Sphere
// category: Particles
vec4 render() {
    vec2 p = P();
    vec3 c = vec3(0); float a = 0.;
    float R = .3 + .03 * uBass * uMotion;
    const int LAT = 22, LON = 40;
    for (int i = 1; i < LAT; i++) {
        float th = float(i) / float(LAT) * PI;
        float e = spec(abs(cos(th)) * .8 + .1);
        float rr = R * (1. + e * .25);
        float y = cos(th) * rr, ring = sin(th) * rr;
        if (abs(p.y - y) > .02) continue;
        for (int j = 0; j < LON; j++) {
            float ph = float(j) / float(LON) * TAU + uTime * .4 * uMotion;
            float z = sin(ph);
            vec2 q = vec2(cos(ph) * ring, y);
            float size = mix(.0025, .006, z * .5 + .5);
            float d = length(p - q);
            float s = smoothstep(size, 0., d) * mix(.25, 1., z * .5 + .5);
            c += pal(th / PI + uTime * .02) * s * (1. + e);
            a += s;
        }
    }
    return vec4(c, a);
}
