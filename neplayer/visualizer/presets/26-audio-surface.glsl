// name: Audio Surface
// category: Particles
vec4 render() {
    vec2 uv = UV();
    vec3 c = vec3(0); float a = 0.;
    const int ROWS = 46;
    for (int k = 0; k < ROWS; k++) {
        float z = float(k) / float(ROWS);
        float persp = mix(1.6, .45, z);
        float baseY = mix(-.05, .62, pow(z, .8));
        float xw = (uv.x - .5) * persp + .5;
        float h = hist(clamp(abs(xw - .5) * 1.8, 0., 1.), z) * .26 * persp;
        float ripple = .02 * sin(xw * 18. + uTime * 1.5 * uMotion + z * 10.) * (1. - z);
        float y = baseY + h + ripple;
        float d = abs(uv.y - y) * uRes.y;
        float dots = smoothstep(.5, .2, abs(fract(xw * 90.) - .5) * 2.);
        float s = smoothstep(2.5, 0., d) * dots * (1.2 - z * .7);
        c += pal(z + xw * .3 + uTime * .02) * s * (1.2 + h * 8.);
        a += s;
    }
    return vec4(c, a);
}
