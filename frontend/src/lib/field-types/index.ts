// descriptorForProp ranks matches (see registry.ts), so order no longer decides
// correctness — only ties, which none of the current kinds' shapes produce.
// Scalars must be registered before group so sub-field fromSchema lookups work.
import './date/date';
import './longtext/longtext';
import './choice/choice';
import './number/number';
import './rating/rating';
import './boolean/boolean';
import './text/text';
import './group/group';
import './quantity/quantity';
import './opaque/opaque';

export {
	register,
	getDescriptor,
	allDescriptors,
	descriptorForProp,
	fieldFromProperty,
	propertyFromField
} from './registry';
