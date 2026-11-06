// name: Energy Wave
// category: Waveform
vec4 render() {
    vec2 uv = UV();
    vec3 c = vec3(0); float a = 0.;
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float e = spec(.04 + fi * .2) ;
        float amp = (.03 + e * .2) * sin(uv.x * PI);           // pinned at the edges
        float y = .5 + amp * sin(uv.x * (3. + fi * 2.2) * PI + uTime * (1.4 + fi * .5) * uMotion + fi);
        float d = abs(uv.y - y) * uRes.y;
        float s = smoothstep(2., 0., d) + exp(-d / ((6. + 14. * e) * uGlow)) * .7;
        c += pal(fi / 5. + uTime * .03) * s;
        a += s;
    }
    return vec4(c, a);
}
