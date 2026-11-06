// name: Vinyl Turntable
// category: Album art
vec4 render() {
    vec2 p = P();
    float r = length(p);
    float R = .36;
    float spin = uTime * .9 * uMotion;
    vec2 q = p * rot(spin);
    float a = atan(q.y, q.x);
    float disc = smoothstep(R + px(), R, r);
    float grooves = .5 + .5 * sin(r * 520.);
    float sheen = pow(abs(sin(a * 2. + 1.)), 8.) * .25;
    vec3 vinyl = vec3(.05) + vec3(.06) * grooves * smoothstep(.13, .15, r) + vec3(sheen) * smoothstep(.13, .3, r);
    float label = smoothstep(.125, .12, r);
    vec3 art = coverAt(q / .25 + .5);
    vec3 col = mix(vinyl, art, label);
    col = mix(col, vec3(.02), smoothstep(.012, .008, r));            // spindle hole
    float t = abs(atan(p.x, p.y)) / PI;
    float e = spec(t * .9);
    float ring = glow(r - R - .015 - e * .06, .006) * (.3 + e * 1.5);
    float a2 = disc + ring;
    return vec4(col * disc + pal(t + uTime * .03) * ring, a2);
}
