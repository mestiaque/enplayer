// name: Cover Pulse
// category: Album art
vec4 render() {
    vec2 p = P();
    float s = .42 + .05 * uBass * uMotion + .03 * uBeat * uMotion;
    vec2 q = p / s + .5;
    vec2 d2 = abs(p) - vec2(s * .5);
    float rr = .03;
    float box = length(max(d2 + rr, 0.)) - rr;
    float inside = smoothstep(px(), -px(), box);
    vec3 art = coverAt(q);
    float shadow = exp(-max(box, 0.) * 22.) * .55;
    float t = (atan(p.x, p.y) / TAU) + .5;
    float w = waveL(t);
    float ringR = s * .78 + w * .04;
    float wr = glow(length(p) - ringR, .004) * (1. - inside);
    return vec4(art * inside + uC2 * wr, inside + shadow * (1. - inside) + wr);
}
