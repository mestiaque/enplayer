// name: Particle Audio Visualizer
// category: Particles
vec4 render() {
    vec2 p = P();
    vec3 c = vec3(0); float a = 0.;
    for (int l = 0; l < 4; l++) {
        float z = fract(float(l) * .25 + uTime * (.08 + .12 * uBass) * uMotion);
        float scale = mix(14., 1.2, z);
        vec2 q = p * scale;
        vec2 cell = floor(q), f = fract(q) - .5;
        float h = hash(cell + float(l) * 31.);
        if (h > .25 + .7 * uDensity) continue;
        vec2 off = (hash2(cell + float(l)) - .5) * .7;
        float e = spec(h);
        float size = (.03 + e * .22) * (.4 + z);
        float d = length(f - off);
        float fade = smoothstep(0., .25, z) * smoothstep(1., .8, z);
        float s = smoothstep(size, 0., d) + exp(-d / (size * 1.8 * uGlow)) * .35;
        c += pal(h + uTime * .02) * s * fade * (.5 + e);
        a += s * fade;
    }
    float core = exp(-length(p) * (9. - 5. * uBass)) * .5;
    return vec4(c + uC2 * core, a + core);
}
