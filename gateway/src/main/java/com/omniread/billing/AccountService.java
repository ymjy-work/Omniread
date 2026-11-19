package com.omniread.billing;

import java.util.List;

import com.omniread.auth.AuthMapper;
import com.omniread.auth.model.UserEntity;
import com.omniread.billing.model.AccountVO;
import com.omniread.billing.model.PlanCatalogEntity;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

	private final AuthMapper authMapper;
	private final PlanCatalogMapper planCatalogMapper;
	private final LedgerMapper ledgerMapper;
	private final PurchaseRecordMapper purchaseRecordMapper;

	public AccountService(AuthMapper authMapper, PlanCatalogMapper planCatalogMapper,
			LedgerMapper ledgerMapper, PurchaseRecordMapper purchaseRecordMapper) {
		this.authMapper = authMapper;
		this.planCatalogMapper = planCatalogMapper;
		this.ledgerMapper = ledgerMapper;
		this.purchaseRecordMapper = purchaseRecordMapper;
	}

	public List<PlanCatalogEntity> listPlans() {
		return planCatalogMapper.findAll();
	}

	/** 周期校验：无周期则建立；到期则回落/续为 free 并重置 100 积分，写 credit_ledger。 */
	@Transactional
	public UserEntity ensureCurrent(UserEntity user) {
		String now = Timestamps.now();
		if (user.getPlanExpiresAt() == null) {
			PlanCatalogEntity plan = requirePlan(user.getPlan());
			String expires = Timestamps.plusDays(now, plan.getDurationDays());
			authMapper.startCycle(user.getId(), user.getPlan(), user.getCredits(), now, expires);
			user.setPlanStartedAt(now);
			user.setPlanExpiresAt(expires);
			return user;
		}
		if (now.compareTo(user.getPlanExpiresAt()) < 0) {
			return user;
		}
		PlanCatalogEntity free = requirePlan("free");
		String oldPlan = user.getPlan();
		long oldCredits = user.getCredits();
		String expires = Timestamps.plusDays(now, free.getDurationDays());
		authMapper.startCycle(user.getId(), "free", free.getCredits(), now, expires);
		ledgerMapper.insertCredit(user.getId(), "free".equals(oldPlan) ? "renew" : "downgrade",
				free.getCredits() - oldCredits, free.getCredits(), oldPlan, now);
		user.setPlan("free");
		user.setCredits(free.getCredits());
		user.setPlanStartedAt(now);
		user.setPlanExpiresAt(expires);
		return user;
	}

	public AccountVO getAccount(long userId) {
		UserEntity user = ensureCurrent(requireUser(userId));
		return toAccount(user);
	}

	@Transactional
	public AccountVO purchase(long userId, String planCode) {
		UserEntity user = ensureCurrent(requireUser(userId));
		PlanCatalogEntity plan = requirePlan(planCode);
		if ("free".equals(plan.getCode())) {
			throw new BusinessException(ErrorCode.BAD_REQUEST, "free 套餐无需购买");
		}
		if (authMapper.deductBalance(userId, plan.getPrice()) == 0) {
			throw new BusinessException(ErrorCode.INSUFFICIENT_BALANCE);
		}
		String now = Timestamps.now();
		String expires = Timestamps.plusDays(now, plan.getDurationDays());
		long oldCredits = user.getCredits();
		double balanceAfter = user.getBalance() - plan.getPrice();
		authMapper.startCycle(userId, plan.getCode(), plan.getCredits(), now, expires);
		ledgerMapper.insertBalance(userId, "purchase", -plan.getPrice(), balanceAfter, plan.getCode(), now);
		ledgerMapper.insertCredit(userId, "purchase", plan.getCredits() - oldCredits, plan.getCredits(),
				plan.getCode(), now);
		purchaseRecordMapper.insert(userId, plan.getCode(), plan.getPrice(), balanceAfter, now);
		user.setPlan(plan.getCode());
		user.setCredits(plan.getCredits());
		user.setBalance(balanceAfter);
		user.setPlanStartedAt(now);
		user.setPlanExpiresAt(expires);
		return toAccount(user);
	}

	private AccountVO toAccount(UserEntity user) {
		return new AccountVO(user.getRole(), user.getPlan(), user.getCredits(), user.getBalance(),
				user.getPlanExpiresAt());
	}

	private UserEntity requireUser(long userId) {
		UserEntity user = authMapper.findUserById(userId);
		if (user == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "用户不存在");
		}
		return user;
	}

	private PlanCatalogEntity requirePlan(String code) {
		PlanCatalogEntity plan = planCatalogMapper.findByCode(code);
		if (plan == null) {
			throw new BusinessException(ErrorCode.BAD_REQUEST, "未知套餐: " + code);
		}
		return plan;
	}
}
