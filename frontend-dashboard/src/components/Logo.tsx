import React from 'react';

interface LogoProps {
  className?: string;
}

/**
 * Icon glyph, copied byte-for-byte from the `d` attribute of the first path in
 * public/ui_design_resources/ds-logo.svg. Do not reformat — it is vector data.
 */
const ICON_PATH =
  'M18.0674 1.53308C20.6133 1.53331 22.6768 3.59744 22.6768 6.14343C22.6767 7.96009 21.6256 9.52997 20.0986 10.2811C20.316 11.0662 20.4346 11.8927 20.4346 12.7469C20.4346 13.6008 20.3159 14.427 20.0986 15.2118C21.6258 15.9628 22.6766 17.5337 22.6768 19.3505C22.6768 21.8965 20.6133 23.9606 18.0674 23.9608C16.3115 23.9608 14.7844 22.9795 14.0059 21.535C13.125 21.8146 12.1873 21.9677 11.2139 21.9677C10.3183 21.9676 9.45347 21.8367 8.63477 21.5985C7.84606 23.0077 6.34004 23.9608 4.61035 23.9608C2.06421 23.9608 0 21.8966 0 19.3505C0.000138621 17.6212 0.952632 16.1148 2.36133 15.326C2.12326 14.5075 1.99316 13.6424 1.99316 12.7469C1.99317 11.8512 2.12307 10.9857 2.36133 10.1669C0.952861 9.37796 5.74043e-05 7.87258 0 6.14343C0 3.59729 2.06421 1.53308 4.61035 1.53308C6.3395 1.53314 7.84488 2.48594 8.63379 3.89441C9.45267 3.65614 10.3181 3.52626 11.2139 3.52625C12.1872 3.52625 13.1251 3.67836 14.0059 3.95789C14.7845 2.51397 16.3119 1.53308 18.0674 1.53308ZM11.2139 4.91003C10.4893 4.91004 9.78807 5.0092 9.12207 5.19324C9.18631 5.49984 9.2207 5.81774 9.2207 6.14343C9.22062 8.68945 7.15637 10.7537 4.61035 10.7538C4.28466 10.7538 3.96676 10.7194 3.66016 10.6552C3.47613 11.3211 3.37696 12.0224 3.37695 12.7469C3.37695 13.4711 3.47631 14.1721 3.66016 14.8378C3.96668 14.7736 4.28475 14.7411 4.61035 14.7411C7.15628 14.7412 9.2205 16.8046 9.2207 19.3505C9.2207 19.6757 9.18615 19.9934 9.12207 20.2997C9.78816 20.4838 10.4892 20.5848 11.2139 20.5848C12.0246 20.5848 12.8065 20.4608 13.542 20.2323C13.4867 19.9469 13.457 19.652 13.457 19.3505C13.4572 16.8045 15.5214 14.7411 18.0674 14.7411C18.3091 14.7411 18.5466 14.7589 18.7783 14.7948C18.9547 14.1418 19.0518 13.4557 19.0518 12.7469C19.0517 12.0379 18.9548 11.3514 18.7783 10.6981C18.5466 10.734 18.3092 10.7538 18.0674 10.7538C15.5213 10.7538 13.4571 8.6895 13.457 6.14343C13.457 5.84151 13.4866 5.54635 13.542 5.26062C12.8066 5.03218 12.0244 4.91003 11.2139 4.91003Z';

/**
 * Geometry lifted from the original ds-logo.svg so the header does not shift.
 *
 *   viewBox        0 0 174 31   (unchanged, so the rendered box is identical)
 *   icon glyph     x 0 → 22.68
 *   wordmark left  x 29.2237    left edge of the old "D"
 *   baseline       y 22.747     bottom of D / S / a / c / e
 *   cap height     19.68        y 3.07 → 22.747
 *
 * Space Grotesk has a cap height of roughly 0.70em, so a 19.68-unit cap height
 * needs font-size 19.68 / 0.70 ≈ 28.1. The old wordmark was this same typeface
 * converted to outlines, so live text in it should land on the same metrics.
 */
const WORDMARK_X = 29.2237;
const BASELINE_Y = 22.747;
const FONT_SIZE = 28.1;

const Logo: React.FC<LogoProps> = ({ className }) => (
  <svg
    className={className}
    width="174"
    height="31"
    viewBox="0 0 174 31"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    role="img"
    aria-label="PulseGrid logo"
  >
    <path d={ICON_PATH} fill="#3FFDE0" />
    <text
      x={WORDMARK_X}
      y={BASELINE_Y}
      fontFamily="'Space Grotesk', sans-serif"
      fontWeight="700"
      fontSize={FONT_SIZE}
    >
      <tspan fill="#3FFDE0">Pulse</tspan>
      <tspan fill="#FFFFFF">Grid</tspan>
    </text>
  </svg>
);

export default Logo;
