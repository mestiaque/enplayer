// name: Galaxy Particles
// category: Particles
vec4 render() {
    vec2 p = P() * 1.15;
    float r = length(p), a = atan(p.y, p.x);
    float spin = uTime * (.08 + .1 * uMid) * uMotion;
    vec3 c = vec3(0); float alpha = 0.;
    for (int l = 0; l < 3; l++) {
        float fl = float(l);
        vec2 q = p * rot(spin * (1. + fl * .5) + fl);
        float rr = length(q), aa = atan(q.y, q.x);
        float arm = .5 + .5 * cos(2. * (aa - log(rr + .02) * 2.2));
        vec2 g = q * (28. + fl * 14.);
        vec2 cell = floor(g), f = fract(g) - .5;
        float h = hash(cell + fl * 13.);
        if (h > .2 + .55 * uDensity) continue;
        vec2 off = (hash2(cell) - .5) * .7;
        float e = spec(clamp(rr * 1.6, 0., 1.));
        float s = smoothstep(.12 + e * .25, 0., length(f - off)) * arm * smoothstep(.75, .1, rr);
        c += pal(rr + h * .3) * s * (.4 + 1.6 * e);
        alpha += s;
    }
    float core = exp(-r * (7. - 3. * uBass)) * (.6 + uBeat * .6);
    float dust = fbm(p * 3. * rot(spin)) * smoothstep(.8, 0., r) * .25;
    return vec4(c + uC2 * core + uC1 * dust, alpha + core + dust);
}
