// name: Radial Frequency Spectrum
// category: Circular
vec4 render() {
    vec2 p = P() * rot(uTime * .05 * uMotion);
    float r = length(p), a = atan(p.x, p.y);   // angle from the top: bass at the top, mirrored left/right
    float t = abs(a) / PI;
    float R = .16 + spec(t * .9) * .32 + .03 * uBass;
    float fill = smoothstep(R + px(), R - px(), r) * smoothstep(.05, .14, r);
    float edge = glow(r - R, .006);
    vec3 col = pal3(r / max(R, .01)) ;
    vec3 c = col * fill * .75 + pal(t + .3) * edge;
    float core = smoothstep(.07, .0, r) * (.4 + uBass);
    return vec4(c + uC2 * core, fill * .75 + edge + core);
}
