// name: Glass Orb
// category: Album art
vec4 render() {
    vec2 p = P();
    float R = .24 + .03 * uBass * uMotion;
    float r = length(p);
    float inside = smoothstep(R + px(), R, r);
    float z = sqrt(max(R * R - r * r, 0.)) / R;
    vec2 refr = p * (1. - z * .35) / R;
    vec3 art = coverAt(refr * .5 + .5) * .9;
    float fres = pow(1. - z, 3.);
    vec2 hl = p - vec2(-.08, .1);
    float spec_ = smoothstep(.08, .0, length(hl)) * .5;
    float inner = exp(-r * 8.) * (.3 + uBeat);
    float t = abs(atan(p.x, p.y)) / PI;
    float aura = glow(r - R - .02 - spec(t) * .07, .008) * (.3 + spec(t) * 1.4);
    vec3 col = art * (.6 + .4 * z) + uC2 * fres * .8 + vec3(spec_) + uC3 * inner;
    return vec4(col * inside + pal(t + uTime * .02) * aura, inside + aura);
}
