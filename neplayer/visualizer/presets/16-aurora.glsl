// name: Plasma / Aurora
// category: Abstract
vec4 render() {
    vec2 uv = UV();
    vec3 c = vec3(0); float a = 0.;
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float e = spec(.08 + fi * .17);
        float t = uTime * (.12 + fi * .03) * uMotion;
        float curve = .55 + .12 * sin(uv.x * (2. + fi) + t * 3. + fi) + .08 * (fbm(vec2(uv.x * 3. + t, fi)) - .5);
        float band = exp(-abs(uv.y - curve - fi * .03) * (14. - 8. * e));
        float streak = .6 + .4 * noise(vec2(uv.x * 60. + fi * 7., t * 4.));
        float above = smoothstep(curve - .02, curve + .35, uv.y) * .5 + .5;
        float s = band * streak * above * (.35 + 1.2 * e);
        c += pal(fi / 5. + uv.x * .2 + t * .2) * s;
        a += s;
    }
    float stars = step(.997, hash(floor(gl_FragCoord.xy / 2.))) * (.4 + .6 * uTreble);
    return vec4(c + vec3(stars), a + stars);
}
