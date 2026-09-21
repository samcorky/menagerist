// Registration order: most-specific types first, text last as fallback.
// Scalars must be registered before group so sub-field fromSchema lookups work.
import './date/date';
import './longtext/longtext';
import './choice/choice';
import './number/number';
import './boolean/boolean';
import './text/text';
import './group/group';
import './opaque/opaque';

export { register, getDescriptor, allDescriptors, descriptorForProp } from './registry';
