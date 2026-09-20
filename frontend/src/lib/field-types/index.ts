// Registration order: most-specific types first, text last as fallback.
// Scalars must be registered before group so sub-field fromSchema lookups work.
import './date';
import './longtext';
import './choice';
import './number';
import './boolean';
import './text';
import './group';

export { register, getDescriptor, allDescriptors, descriptorForProp } from './registry';
