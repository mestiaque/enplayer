// name: Silk Ribbons
// category: Waveform
vec4 render() {
    vec2 uv = UV();
    vec3 c = vec3(0); float a = 0.;
    for (int i = 0; i < 7; i++) {
        float fi = float(i);
        float e = spec(.05 + fi * .12);
        float y = .5 + .18 * sin(uv.x * 3. + uTime * (.5 + fi * .08) * uMotion + fi * .9) * (.5 + e)
                     + .05 * sin(uv.x * 9. - uTime * .7 * uMotion + fi);
        float w = .01 + .03 * e;
        float d = uv.y - y;
        float band = smoothstep(w, 0., abs(d)) * (.4 + .6 * sin(uv.x * 2. + fi));
        float edge = line(d - w * .8, .0015);
        c += pal(fi / 7. + uv.x * .2) * (band * .45 + edge * .7);
        a += band * .45 + edge * .7;
    }
    return vec4(c, a);
}
