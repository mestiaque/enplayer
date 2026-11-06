#version 330 core
// Shared prelude for every visualizer preset. A preset only implements
//     vec4 render();   // rgb colour + alpha (coverage) for gl_FragCoord
// and reads real audio data through the helpers below.
out vec4 fragColor;
uniform vec2 uRes;          // framebuffer size in pixels
uniform float uTime;        // seconds, scaled by "animation speed"
uniform sampler2D uSpec;    // 128 x 4 : bands, left bands, right bands, peak caps (0..1)
uniform sampler2D uWave;    // 512 x 2 : left, right waveform (-1..1)
uniform sampler2D uHist;    // 128 x 64: spectrum history, row 0 = now
uniform float uBass, uMid, uTreble, uLevel, uBeat;
uniform vec3 uC1, uC2, uC3; // colour theme
uniform float uGlow, uBright, uDensity, uMotion;
uniform vec3 uBg;
uniform int uBgMode;        // 0 solid, 1 transparent (album art behind), 2 gradient
uniform sampler2D uCover;   // album art (square), when uHasCover > 0.5
uniform float uHasCover;

#define PI 3.14159265
#define TAU 6.28318531

float spec(float x)  { return texture(uSpec, vec2(clamp(x, 0., 1.) * (127. / 128.) + .5 / 128., .125)).r; }
float specL(float x) { return texture(uSpec, vec2(clamp(x, 0., 1.) * (127. / 128.) + .5 / 128., .375)).r; }
float specR(float x) { return texture(uSpec, vec2(clamp(x, 0., 1.) * (127. / 128.) + .5 / 128., .625)).r; }
float peak(float x)  { return texture(uSpec, vec2(clamp(x, 0., 1.) * (127. / 128.) + .5 / 128., .875)).r; }
float waveL(float x) { return texture(uWave, vec2(clamp(x, 0., 1.), .25)).r; }
float waveR(float x) { return texture(uWave, vec2(clamp(x, 0., 1.), .75)).r; }
float wave(float x)  { return .5 * (waveL(x) + waveR(x)); }
float hist(float x, float age) { return texture(uHist, vec2(clamp(x, 0., 1.), clamp(age, 0., 1.))).r; }

vec2 P() { return (gl_FragCoord.xy - .5 * uRes) / uRes.y; }   // centred, aspect-correct
vec2 UV() { return gl_FragCoord.xy / uRes; }
float px() { return 1. / uRes.y; }                              // one pixel in P() units

// Album art at uv (0..1, origin bottom-left); themed gradient when the track has no cover.
vec3 coverAt(vec2 uv) {
    vec3 fallback = mix(mix(uC1, uC2, uv.x), uC3, uv.y * .6) * .9;
    return uHasCover > .5 ? texture(uCover, clamp(uv, 0., 1.)).rgb : fallback;
}

vec3 pal(float t) {
    t = fract(t);
    return t < .5 ? mix(uC1, uC2, t * 2.) : mix(uC2, uC3, (t - .5) * 2.);
}
vec3 pal3(float t) { // C1 -> C2 -> C3 without wrapping
    t = clamp(t, 0., 1.);
    return t < .5 ? mix(uC1, uC2, t * 2.) : mix(uC2, uC3, (t - .5) * 2.);
}
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
vec2 hash2(vec2 p) { return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3. - 2. * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
    float v = 0., a = .5;
    for (int i = 0; i < 5; i++) { v += a * noise(p); p = p * 2.03 + 17.1; a *= .5; }
    return v;
}
float glow(float d, float w) { return exp(-abs(d) / max(w * uGlow, 1e-4)); }
float line(float d, float w) { return smoothstep(w, 0., abs(d)); }
float sdSeg(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a, ba = b - a;
    return length(pa - ba * clamp(dot(pa, ba) / dot(ba, ba), 0., 1.));
}
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }

vec4 render();

void main() {
    vec4 c = render();
    c.rgb = clamp(c.rgb * uBright, 0., 4.);
    c.a = clamp(c.a, 0., 1.);
    if (uBgMode == 1) {                       // album art shows through
        fragColor = vec4(min(c.rgb, 1.) * c.a, c.a);
    } else {
        vec3 bg = uBg;
        if (uBgMode == 2) {
            vec2 uv = UV();
            bg = mix(uBg, mix(uC1, uC3, uv.x) * .22 + uBg, smoothstep(1.2, 0., length(uv - vec2(.5, .3))));
        }
        fragColor = vec4(min(mix(bg, c.rgb, c.a), 1.), 1.);
    }
}
