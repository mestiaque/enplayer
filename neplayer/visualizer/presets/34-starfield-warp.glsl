// name: Starfield Warp
// category: Particles
vec4 render() {
    vec2 p = P();
    vec3 c = vec3(0); float a = 0.;
    float speed = (.2 + 1.2 * uLevel + .8 * uBeat) * uMotion;
    for (int l = 0; l < 5; l++) {
        float fl = float(l);
        float z = fract(fl * .2 + uTime * speed * .2);
        vec2 q = p / (z * 1.4 + .02);
        vec2 cell = floor(q * 4.), f = fract(q * 4.) - .5;
        float h = hash(cell + fl * 9.);
        if (h > .2 + .6 * uDensity) continue;
        vec2 off = (hash2(cell + fl) - .5) * .6;
        vec2 dir = normalize(q + 1e-4);
        vec2 d = f - off;
        float along = dot(d, dir), across = abs(dot(d, vec2(-dir.y, dir.x)));
        float streak = smoothstep(.03, 0., across) * smoothstep(.0, -.25 * (1. - z) * speed, along) * smoothstep(.4, .0, abs(along));
        float s = streak * smoothstep(1., .5, z) * (.5 + spec(h));
        c += pal(h) * s;
        a += s;
    }
    return vec4(c * 1.5, a);
}
