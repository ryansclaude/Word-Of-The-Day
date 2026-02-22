import {makeScene2D, Rect, Txt, Circle, Line} from '@motion-canvas/2d';
import {
  createRef,
  all,
  chain,
  waitFor,
  Color,
  Vector2,
  easeInOutCubic,
  linear,
} from '@motion-canvas/core';

import data from '../../../data_bridge.json';

export default makeScene2D(function* (view) {
  // ── Layout: 1080x1920 (9:16) ──
  view.fill(data.background_hex);

  // ── Word Title ──
  const wordRef = createRef<Txt>();
  view.add(
    <Txt
      ref={wordRef}
      text={data.word.toUpperCase()}
      fontFamily="'Inter', 'Helvetica Neue', sans-serif"
      fontWeight={800}
      fontSize={120}
      fill={'#ffffff'}
      y={-500}
      opacity={0}
      letterSpacing={8}
    />,
  );

  // ── On-screen text lines ──
  const line1Ref = createRef<Txt>();
  const line2Ref = createRef<Txt>();
  view.add(
    <Txt
      ref={line1Ref}
      text=""
      fontFamily="'Inter', 'Helvetica Neue', sans-serif"
      fontWeight={400}
      fontSize={56}
      fill={'#cccccc'}
      y={-200}
      opacity={0}
      textAlign="center"
      textWrap
      width={900}
    />,
  );
  view.add(
    <Txt
      ref={line2Ref}
      text=""
      fontFamily="'Inter', 'Helvetica Neue', sans-serif"
      fontWeight={400}
      fontSize={56}
      fill={'#cccccc'}
      y={0}
      opacity={0}
      textAlign="center"
      textWrap
      width={900}
    />,
  );

  // ── Circular Progress Timer ──
  const progressRef = createRef<Circle>();
  const timerTextRef = createRef<Txt>();
  view.add(
    <Circle
      ref={progressRef}
      width={120}
      height={120}
      y={600}
      stroke={'#ffffff'}
      lineWidth={4}
      opacity={0.6}
      startAngle={-90}
      endAngle={-90}
    />,
  );
  view.add(
    <Txt
      ref={timerTextRef}
      text="15"
      fontFamily="'Inter', 'Helvetica Neue', sans-serif"
      fontWeight={600}
      fontSize={36}
      fill={'#ffffff'}
      y={600}
      opacity={0.6}
    />,
  );

  // ── Decorative accent line ──
  const accentRef = createRef<Line>();
  const accentColor = new Color(data.background_hex).brighten(1.5).hex();
  view.add(
    <Line
      ref={accentRef}
      points={[new Vector2(-200, -350), new Vector2(200, -350)]}
      stroke={accentColor}
      lineWidth={3}
      opacity={0}
    />,
  );

  // ── Typewriter helper ──
  function* typewriter(ref: ReturnType<typeof createRef<Txt>>, text: string, duration: number) {
    const chars = text.split('');
    const interval = duration / chars.length;
    ref().opacity(1);
    for (let i = 0; i <= chars.length; i++) {
      ref().text(text.slice(0, i));
      yield* waitFor(interval);
    }
  }

  // ── Animation Timeline (15 seconds total) ──

  // 0s–1.5s: Word pops in with scale
  yield* all(
    wordRef().opacity(1, 0.8, easeInOutCubic),
    wordRef().y(-500, 0).to(-500, 0.01).to(-480, 0.8, easeInOutCubic),
  );
  yield* waitFor(0.5);

  // 1.5s–2s: Accent line fades in
  yield* accentRef().opacity(0.5, 0.5, easeInOutCubic);

  // 2s–6s: First on-screen text typewriter
  yield* typewriter(line1Ref, data.on_screen_text[0], 3.0);
  yield* waitFor(1.0);

  // 6s–10s: Second on-screen text typewriter
  yield* typewriter(line2Ref, data.on_screen_text[1], 3.0);
  yield* waitFor(1.0);

  // 10s–15s: Progress timer runs down
  // Start the circular timer (runs from beginning but visual shows last 5s)
  yield* all(
    progressRef().endAngle(270, 5, linear),
    chain(
      ...[5, 4, 3, 2, 1, 0].map((n) =>
        chain(
          () => {timerTextRef().text(String(n)); return undefined as any;},
          waitFor(n > 0 ? 1 : 0),
        ),
      ),
    ),
  );

  // Final: Everything fades out
  yield* all(
    wordRef().opacity(0, 0.5),
    line1Ref().opacity(0, 0.5),
    line2Ref().opacity(0, 0.5),
    accentRef().opacity(0, 0.5),
    progressRef().opacity(0, 0.5),
    timerTextRef().opacity(0, 0.5),
  );
});
