// name: Beat Fireworks
// category: Particles
vec4 render() {
    vec2 p = P();
    vec3 c = vec3(0); float a = 0.;
    for (int b = 0; b < 4; b++) {
        float fb = float(b);
        float cycle = uTime * .4 * uMotion + fb * .25;
        float id = floor(cycle);
        float t = fract(cycle);
        vec2 center = (hash2(vec2(id, fb)) - .5) * vec2(1.1, .55) + vec2(0., .05);
        float power = .6 + spec(hash(vec2(id, fb + 3.)) * .7) * .8 + uBeat * .3;
        float hue = hash(vec2(id, fb + 7.));
        float fade = pow(1. - t, 1.5);
        for (int k = 0; k < 28; k++) {
            float fk = float(k);
            float ang = fk / 28. * TAU + hash(vec2(id, fk)) * .2;
            vec2 dir = vec2(cos(ang), sin(ang)) * (.8 + .4 * hash(vec2(fk, id)));
            float s = 0.;
            for (int j = 0; j < 4; j++) {                    // short trail
                float tt = max(t - float(j) * .025, 0.);
                vec2 pos = center + dir * (1. - exp(-tt * 4.)) * .26 * power - vec2(0., tt * tt * .1);
                float d = length(p - pos);
                s += (smoothstep(.009, 0., d) + glow(d, .006) * .5) * (1. - float(j) * .22);
            }
            c += pal(hue + fk * .008) * s * fade;
            a += s * fade;
        }
        float flash = exp(-length(p - center) * 12.) * exp(-t * 10.);
        c += vec3(1.) * flash; a += flash;
    }
    return vec4(c, a);
}
